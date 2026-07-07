"""权限系统 - 融合 Claude Code 三层权限体系。

三层体系：
1. Skill 权限层 - allowed_tools 限定工具集合（已有）
2. 工具规则层 - allow/deny/ask 静态规则，从 settings 读取
3. 运行时确认层 - 用户确认，支持 "Yes, and don't ask again for this session"

规则优先级：deny > ask > allow，且 policy > project > user。
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Tool, ToolPermissionLevel

logger = logging.getLogger(__name__)


class RuleBehavior(str, Enum):
    """规则行为 - 对应 Claude Code 的 allow/deny/ask。"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class RuleSource(str, Enum):
    """规则来源 - 按优先级从高到低。"""
    POLICY = "policy"      # 企业策略，最高优先级
    PROJECT = "project"    # 项目级 .claude/settings.json
    USER = "user"          # 用户级 ~/.claude/settings.json
    SESSION = "session"    # 会话临时规则


@dataclass
class PermissionRule:
    """权限规则 - 匹配工具名（支持通配符）和参数。"""
    tool_pattern: str           # 工具匹配模式，如 "write_file"、"file_*"、"*"
    arg_pattern: Optional[str] = None  # 参数匹配模式（可选）
    behavior: RuleBehavior = RuleBehavior.ASK
    source: RuleSource = RuleSource.SESSION

    def matches(self, tool_name: str, args: Any) -> bool:
        """检查规则是否匹配给定的工具调用。"""
        # 工具名匹配
        if self.tool_pattern == "*":
            matches_tool = True
        elif "*" in self.tool_pattern:
            import fnmatch
            matches_tool = fnmatch.fnmatch(tool_name, self.tool_pattern)
        else:
            matches_tool = (self.tool_pattern == tool_name)

        if not matches_tool:
            return False

        # 参数匹配（如果有）
        if self.arg_pattern:
            args_str = json.dumps(_args_to_dict(args), ensure_ascii=False, default=str)
            if "*" in self.arg_pattern:
                import fnmatch
                return fnmatch.fnmatch(args_str, self.arg_pattern)
            return self.arg_pattern in args_str

        return True

    @property
    def priority(self) -> int:
        """规则优先级（用于排序）。"""
        source_priority = {
            RuleSource.POLICY: 100,
            RuleSource.PROJECT: 80,
            RuleSource.USER: 60,
            RuleSource.SESSION: 20,
        }
        behavior_priority = {
            RuleBehavior.DENY: 3,
            RuleBehavior.ASK: 2,
            RuleBehavior.ALLOW: 1,
        }
        return source_priority[self.source] * 10 + behavior_priority[self.behavior]


def _args_to_dict(args: Any) -> Dict[str, Any]:
    """把 args 转成字典。"""
    if hasattr(args, "model_dump"):
        return args.model_dump()
    if isinstance(args, dict):
        return args
    return {}


@dataclass
class PermissionResult:
    """权限检查结果 - 增强版，支持规则回写建议。"""
    behavior: str
    updated_input: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    matched_rule: Optional[PermissionRule] = None
    suggested_rule: Optional[PermissionRule] = None  # 可回写的规则建议（session 级别）


class PermissionChecker:
    """权限检查器 - 融合 Claude Code 三层权限体系。

    检查顺序：
    1. 静态规则层（按优先级 deny > ask > allow）
    2. 工具默认权限级别（ToolPermissionLevel）
    3. 运行时确认（若需要）
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        user_home: Optional[Path] = None,
    ):
        self.project_root = project_root or self._detect_project_root()
        self.user_home = user_home or Path.home()

        self._rules: List[PermissionRule] = []
        self._tool_overrides: Dict[str, ToolPermissionLevel] = {}

        # 加载规则
        self._load_rules()

    def _detect_project_root(self) -> Path:
        """自动检测项目根目录。"""
        import sys
        for p in sys.path:
            candidate = Path(p)
            if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
                return candidate
        return Path.cwd()

    def _load_rules(self):
        """从 settings 文件加载规则。"""
        # 1. 用户级 ~/.claude/settings.json
        user_settings = self.user_home / ".claude" / "settings.json"
        if user_settings.exists():
            self._load_rules_from_file(user_settings, RuleSource.USER)

        # 2. 项目级 .claude/settings.json
        project_settings = self.project_root / ".claude" / "settings.json"
        if project_settings.exists():
            self._load_rules_from_file(project_settings, RuleSource.PROJECT)

        # 3. 默认规则（内置）
        self._load_default_rules()

    def _load_rules_from_file(self, path: Path, source: RuleSource):
        """从 JSON 文件加载规则。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "permissions" in data and "rules" in data["permissions"]:
                for rule_data in data["permissions"]["rules"]:
                    rule = PermissionRule(
                        tool_pattern=rule_data.get("tool", "*"),
                        arg_pattern=rule_data.get("args"),
                        behavior=RuleBehavior(rule_data.get("behavior", "ask")),
                        source=source,
                    )
                    self._rules.append(rule)
                logger.debug(f"Loaded {len(self._rules)} rules from {path}")
        except Exception as e:
            logger.warning(f"Failed to load rules from {path}: {e}")

    def _load_default_rules(self):
        """加载默认规则 - 对应 Claude Code 的风险等级默认值。"""
        # Read 类工具默认 allow
        self._rules.append(PermissionRule(
            tool_pattern="read_file",
            behavior=RuleBehavior.ALLOW,
            source=RuleSource.POLICY,
        ))
        self._rules.append(PermissionRule(
            tool_pattern="list_files",
            behavior=RuleBehavior.ALLOW,
            source=RuleSource.POLICY,
        ))
        self._rules.append(PermissionRule(
            tool_pattern="grep",
            behavior=RuleBehavior.ALLOW,
            source=RuleSource.POLICY,
        ))
        self._rules.append(PermissionRule(
            tool_pattern="glob",
            behavior=RuleBehavior.ALLOW,
            source=RuleSource.POLICY,
        ))

        # Edit/Write 类工具默认 ask
        self._rules.append(PermissionRule(
            tool_pattern="write_file",
            behavior=RuleBehavior.ASK,
            source=RuleSource.POLICY,
        ))
        self._rules.append(PermissionRule(
            tool_pattern="edit_file",
            behavior=RuleBehavior.ASK,
            source=RuleSource.POLICY,
        ))

        # 网络类工具默认 ask
        self._rules.append(PermissionRule(
            tool_pattern="web_fetch",
            behavior=RuleBehavior.ASK,
            source=RuleSource.POLICY,
        ))

    def add_rule(self, rule: PermissionRule):
        """添加规则（会话级）- 用于 "Yes, and don't ask again for this session"。"""
        self._rules.append(rule)

    def persist_rule(self, rule: PermissionRule, target: RuleSource = RuleSource.USER):
        """持久化规则到 settings 文件（可选功能，不是默认行为）。"""
        if target == RuleSource.POLICY:
            logger.warning("Cannot persist to POLICY source")
            return

        if target == RuleSource.USER:
            settings_dir = self.user_home / ".claude"
        elif target == RuleSource.PROJECT:
            settings_dir = self.project_root / ".claude"
        else:
            return

        settings_dir.mkdir(exist_ok=True)
        settings_file = settings_dir / "settings.json"

        data = {}
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        if "permissions" not in data:
            data["permissions"] = {}
        if "rules" not in data["permissions"]:
            data["permissions"]["rules"] = []

        # 添加规则
        data["permissions"]["rules"].append({
            "tool": rule.tool_pattern,
            "args": rule.arg_pattern,
            "behavior": rule.behavior.value,
        })

        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Persisted rule to {settings_file}")
        except Exception as e:
            logger.warning(f"Failed to persist rule: {e}")

    def set_tool_permission(self, tool_name: str, level: ToolPermissionLevel):
        """设置特定工具的权限级别（兼容旧 API）。"""
        self._tool_overrides[tool_name] = level

    async def check_permission(
        self,
        tool: Tool,
        args: Any,
        context: Dict[str, Any],
    ) -> PermissionResult:
        """检查权限 - 融合三层体系。

        顺序：
        1. 检查静态规则（优先级排序）
        2. 检查工具级别 override
        3. 检查工具默认 permission_level
        4. MCP 工具默认 ask
        """
        # 第 1 步：静态规则层
        matched_rule = self._find_matching_rule(tool.name, args)
        if matched_rule:
            if matched_rule.behavior == RuleBehavior.DENY:
                return PermissionResult(
                    behavior="deny",
                    reason=f"Denied by {matched_rule.source.value} rule",
                    matched_rule=matched_rule,
                )
            if matched_rule.behavior == RuleBehavior.ALLOW:
                return PermissionResult(
                    behavior="allow",
                    reason=f"Allowed by {matched_rule.source.value} rule",
                    matched_rule=matched_rule,
                    updated_input=args.model_dump() if hasattr(args, 'model_dump') else None,
                )
            if matched_rule.behavior == RuleBehavior.ASK:
                # 建议回写规则（session 级别）
                suggested_rule = PermissionRule(
                    tool_pattern=tool.name,
                    arg_pattern=None,  # 不限制参数，简化处理
                    behavior=RuleBehavior.ALLOW,
                    source=RuleSource.SESSION,
                )
                return PermissionResult(
                    behavior="require_confirmation",
                    reason=f"Asked by {matched_rule.source.value} rule",
                    matched_rule=matched_rule,
                    suggested_rule=suggested_rule,
                )

        # 第 2 步：工具级别 override
        level = self._tool_overrides.get(tool.name, tool.permission_level)

        if level == ToolPermissionLevel.DENIED:
            return PermissionResult(
                behavior="deny",
                reason="Tool is denied by policy",
            )

        if level == ToolPermissionLevel.REQUIRES_CONFIRM:
            suggested_rule = PermissionRule(
                tool_pattern=tool.name,
                behavior=RuleBehavior.ALLOW,
                source=RuleSource.SESSION,
            )
            return PermissionResult(
                behavior="require_confirmation",
                reason="Tool requires confirmation",
                suggested_rule=suggested_rule,
            )

        # 第 3 步：MCP 工具默认 ask
        if tool.is_mcp:
            suggested_rule = PermissionRule(
                tool_pattern=tool.name,
                behavior=RuleBehavior.ALLOW,
                source=RuleSource.SESSION,
            )
            return PermissionResult(
                behavior="require_confirmation",
                reason="MCP tools require confirmation by default",
                suggested_rule=suggested_rule,
            )

        # 默认 allow
        return PermissionResult(
            behavior="allow",
            reason="Default allow",
            updated_input=args.model_dump() if hasattr(args, 'model_dump') else None,
        )

    def _find_matching_rule(self, tool_name: str, args: Any) -> Optional[PermissionRule]:
        """找到优先级最高的匹配规则。"""
        matching_rules = [r for r in self._rules if r.matches(tool_name, args)]
        if not matching_rules:
            return None
        # 按优先级排序，取最高
        matching_rules.sort(key=lambda r: r.priority, reverse=True)
        return matching_rules[0]

    def list_rules(self) -> List[PermissionRule]:
        """列出所有规则（按优先级排序）。"""
        rules = list(self._rules)
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules
