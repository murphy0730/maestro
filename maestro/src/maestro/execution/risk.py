"""保守的 Shell 风险分类。

它只用于权限决策和降低损害，不是 OS 安全边界。后续可在不改变调用协议的
情况下用 Bash/PowerShell AST 解析器替换这里的词法实现。
"""

import re
import shlex

from .models import CommandRisk


_DENY = {
    "download_and_execute": [
        r"\b(?:curl|wget)\b[^|;]*(?:\||;)\s*(?:ba|z|k)?sh\b",
        r"\b(?:irm|invoke-restmethod|iwr|invoke-webrequest)\b[^|;]*\|\s*(?:iex|invoke-expression)\b",
    ],
    "privilege_escalation": [r"\bsudo\b", r"\bstart-process\b[^\n]*-verb\s+runas\b"],
    "disk_destruction": [r"\bformat(?:\.com)?\b", r"\bclear-disk\b", r"\bdd\b[^\n]*\bof=/dev/"],
    "guard_tampering": [r"\b(?:set-mppreference|netsh)\b[^\n]*(?:disable|firewall)"],
    "credential_access": [r"\.ssh[/\\]", r"\b(?:security|cmdkey)\b[^\n]*(?:find|list|generic-password)"],
    "reverse_shell": [r"/dev/tcp/", r"\bncat?\b[^\n]*\s-e\s", r"tcpclient\s*\("],
}

_ASK = {
    "file_delete": [r"\b(?:rm|del|erase|rmdir|remove-item)\b"],
    "file_write": [r"(?:^|\s)(?:>|>>)(?:\s|$)", r"\b(?:set-content|out-file|copy-item|move-item)\b"],
    "network": [r"\b(?:curl|wget|irm|iwr|invoke-webrequest|invoke-restmethod)\b"],
    "package_install": [r"\b(?:pip|npm|pnpm|yarn|cargo)\b[^\n]*(?:install|add)\b"],
    "state_change": [r"\bgit\s+(?:commit|push|reset|clean|checkout|switch)\b", r"\breg(?:\.exe)?\s+(?:add|delete)\b"],
    "dynamic_execution": [r"\b(?:eval|iex|invoke-expression)\b", r"\b(?:bash|sh|zsh|powershell|pwsh)\s+(?:-c|-command|/c)\b"],
    "process_start": [r"\b(?:start-process|start-job|schtasks|new-service)\b"],
}

_READ_ONLY = {
    "bash": {"ls", "pwd", "find", "rg", "grep", "cat", "head", "tail", "wc", "stat", "git"},
    "powershell": {"get-childitem", "get-content", "get-process", "get-service", "get-location", "select-string"},
}


def _matches(command: str, rules: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    categories: list[str] = []
    matched: list[str] = []
    for category, patterns in rules.items():
        for pattern in patterns:
            if re.search(pattern, command, re.IGNORECASE):
                categories.append(category)
                matched.append(f"{category}:{pattern}")
                break
    return categories, matched


def _commands(command: str) -> list[str]:
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return []
    return [parts[0].lower()] if parts else []


def classify_command(command: str, shell: str) -> CommandRisk:
    text = command.strip()
    commands = _commands(text)
    deny_categories, deny_rules = _matches(text, _DENY)
    if deny_categories:
        return CommandRisk("deny", deny_categories, "命中禁止执行的危险命令模式", commands, deny_rules)

    ask_categories, ask_rules = _matches(text, _ASK)
    if ask_categories:
        return CommandRisk("ask", ask_categories, "命令可能修改状态、访问网络或动态执行代码", commands, ask_rules)

    # 在完整 AST 解析器接入前，对变量展开、命令替换、brace expansion、重定向和
    # 复合命令一律不自动放行，避免 parser differential 把危险的后续命令 (或紧贴
    # 文件名的 `>file` 写重定向) 藏在只读前缀后。
    parse_complete = bool(commands) and not re.search(
        r"[$`<>]|\{[^}]*\}|\^|&&|\|\||[;|]", text
    )
    if not parse_complete:
        return CommandRisk("ask", ["incomplete_parse"], "无法完整静态分析命令", commands, ["parse:incomplete"], False)

    base = commands[0] if commands else ""
    if base == "git" and not re.match(r"^git\s+(?:status|log|diff|show|branch)(?:\s|$)", text, re.I):
        return CommandRisk("ask", ["unclassified"], "Git 子命令未被证明为只读", commands, ["git:unknown"])
    if base in _READ_ONLY.get(shell, set()):
        return CommandRisk("allow", ["read_only"], "命令被识别为只读查询", commands, [f"readonly:{base}"])
    return CommandRisk("ask", ["unclassified"], "执行代码无法仅靠命令名称证明为只读", commands, ["default:ask"])
