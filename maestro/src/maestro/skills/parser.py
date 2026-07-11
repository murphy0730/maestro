from __future__ import annotations
import io
import re
import zipfile
from pathlib import Path
import yaml
from pydantic import ValidationError
from maestro.skills.schemas import (
    SkillCapabilityReport,
    SkillFrontmatter,
    SkillValidationError,
    SkillValidationReport,
)

_BODY_MAX = 32 * 1024
_ZIP_MAX_MEMBERS = 50
_ZIP_MAX_TOTAL = 10 * 1024 * 1024
_IGNORED_PACKAGE_PARTS = {".DS_Store", "__MACOSX"}

FIELD_ALIASES = {
    "display-name": "display_name",
    "when-to-use": "when_to_use",
    "allowed-tools": "allowed_tools",
    "user-invocable": "user_invocable",
    "disable-model-invocation": "disable_model_invocation",
    "argument-hint": "argument_hint",
}
KNOWN_FIELDS = set(SkillFrontmatter.model_fields)
DEFAULT_TOOL_ALIASES = {
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "edit_file",
    "Bash": "bash",
    "PowerShell": "powershell",
    "Glob": "glob",
    "Grep": "grep",
    "WebFetch": "web_fetch",
    "TodoWrite": "todo_write",
}


def _normalize_name(value: object) -> tuple[object, str | None]:
    if not isinstance(value, str):
        return value, None
    normalized = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", value.lower())).strip("-")
    if len(normalized) > 32:
        normalized = normalized[:32].rstrip("-")
    if normalized and not normalized[0].isalpha():
        normalized = f"skill-{normalized}"[:32].rstrip("-")
    if len(normalized) == 1:
        normalized = f"{normalized}-skill"
    return normalized, (f"技能名称已从 {value!r} 规范化为 {normalized!r}" if normalized != value else None)


def normalize_frontmatter(data: dict) -> tuple[dict, list[str]]:
    """Normalize common Codex/Claude frontmatter without silently losing semantics."""
    out: dict = {}
    warnings: list[str] = []
    extensions: dict = {}
    for raw_key, value in data.items():
        key = FIELD_ALIASES.get(str(raw_key), str(raw_key))
        if key != raw_key:
            warnings.append(f"字段 {raw_key!r} 已转换为 {key!r}")
        if key == "metadata" and isinstance(value, dict):
            extensions["metadata"] = value
        elif key in KNOWN_FIELDS:
            out[key] = value
        else:
            extensions[key] = value
            warnings.append(f"未识别字段 {raw_key!r} 已保留在 extensions 中，但不会自动生效")
    out["name"], name_warning = _normalize_name(out.get("name"))
    if name_warning:
        warnings.append(name_warning)
    allowed = out.get("allowed_tools")
    if isinstance(allowed, str):
        out["allowed_tools"] = [part for part in re.split(r"[\s,]+", allowed) if part]
        warnings.append("allowed_tools 字符串已转换为列表")
    scripts = out.get("scripts")
    if isinstance(scripts, str):
        out["scripts"] = [scripts]
    if extensions:
        out["extensions"] = extensions
    return out, warnings


def parse_skill_md(
    text: str,
    max_bytes: int = _BODY_MAX,
    *,
    compatible: bool = True,
    warnings: list[str] | None = None,
) -> tuple[SkillFrontmatter, str]:
    if not text.startswith("---"):
        raise SkillValidationError("frontmatter 必须以 '---' 开头")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillValidationError("frontmatter 缺少结束 '---'")
    fm_raw, body = parts[1], parts[2].lstrip("\n")
    try:
        data = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        raise SkillValidationError(f"frontmatter YAML 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise SkillValidationError("frontmatter 必须解析为 dict")
    if compatible:
        data, normalization_warnings = normalize_frontmatter(data)
        if warnings is not None:
            warnings.extend(normalization_warnings)
    try:
        fm = SkillFrontmatter(**data)
    except ValidationError as e:
        raise SkillValidationError(str(e)) from e
    if not body.strip():
        raise SkillValidationError("正文不能为空")
    if len(body.encode("utf-8")) > max_bytes:
        raise SkillValidationError(f"正文需 ≤{max_bytes // 1024}KB")
    return fm, body


def extract_package(
    data: bytes,
    filename: str,
    max_bytes: int = _BODY_MAX,
    *,
    warnings: list[str] | None = None,
) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    name = filename.lower()
    if name.endswith(".md"):
        fm, body = parse_skill_md(data.decode("utf-8"), max_bytes, warnings=warnings)
        return fm, body, {}
    if name.endswith(".zip"):
        return _extract_zip(data, max_bytes, warnings=warnings)
    raise SkillValidationError("仅支持 .md / .zip 后缀")


def _extract_zip(
    data: bytes, max_bytes: int = _BODY_MAX, *, warnings: list[str] | None = None
) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    bio = io.BytesIO(data)
    try:
        zf = zipfile.ZipFile(bio)
    except zipfile.BadZipFile as e:
        raise SkillValidationError(f"zip 解压失败: {e}") from e
    members = [
        i for i in zf.infolist()
        if not i.is_dir() and not any(part in _IGNORED_PACKAGE_PARTS for part in Path(i.filename).parts)
    ]
    if len(members) > _ZIP_MAX_MEMBERS:
        raise SkillValidationError(f"zip 成员数 >{_ZIP_MAX_MEMBERS}")
    files: dict[str, bytes] = {}
    total = 0
    for info in members:
        n = info.filename
        if n.startswith("/") or ".." in Path(n).parts:
            raise SkillValidationError(f"zip 含不安全路径: {n}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise SkillValidationError(f"zip 含符号链接: {n}")
        content = zf.read(n)
        total += len(content)
        if total > _ZIP_MAX_TOTAL:
            raise SkillValidationError("zip 解压后 >10MB")
        files[n] = content
    skill_path = _find_skill_md(files)
    if skill_path is None:
        raise SkillValidationError("zip 缺少 SKILL.md")
    prefix = str(Path(skill_path).parent)
    attachments: dict[str, bytes] = {}
    for path, content in files.items():
        rel = path[len(prefix) + 1:] if prefix != "." and path.startswith(prefix + "/") else path
        if rel == "SKILL.md" or path == skill_path:
            continue
        attachments[rel] = content
    fm, body = parse_skill_md(
        files[skill_path].decode("utf-8"), max_bytes, warnings=warnings
    )
    return fm, body, attachments


def _find_skill_md(files: dict[str, bytes]) -> str | None:
    if "SKILL.md" in files:
        return "SKILL.md"
    # 唯一顶层目录内
    top_dirs = {p.split("/", 1)[0] for p in files if "/" in p}
    if len(top_dirs) == 1:
        only = next(iter(top_dirs))
        candidate = f"{only}/SKILL.md"
        if candidate in files:
            return candidate
    return None


def validate_allowed_tools(
    fm: SkillFrontmatter,
    registered: set[str],
    default: list[str],
    named: set[str],
) -> list[str]:
    allowed = fm.allowed_tools if fm.allowed_tools is not None else list(default)
    unknown = [t for t in allowed if t not in registered]
    if unknown:
        raise SkillValidationError(f"allowed_tools 含未注册工具: {unknown}")
    bad = []
    for tool, names in fm.tool_preconditions.items():
        if tool not in allowed:
            bad.append(f"tool_preconditions key '{tool}' 不在 allowed_tools 内")
        for n in names:
            if n not in named:
                bad.append(f"tool_preconditions['{tool}'] 断言名 '{n}' 未注册")
    if bad:
        raise SkillValidationError("; ".join(bad))
    return allowed


def validate_skill_package(
    data: bytes,
    filename: str,
    registered: set[str],
    default: list[str],
    named: set[str],
    max_bytes: int = _BODY_MAX,
    tool_aliases: dict[str, str] | None = None,
) -> tuple[SkillFrontmatter | None, str | None, dict[str, bytes], SkillValidationReport]:
    """Preflight a package and return structured compatibility diagnostics."""
    warnings: list[str] = []
    errors: list[str] = []
    mapping: dict[str, str] = {}
    try:
        fm, body, attachments = extract_package(
            data, filename, max_bytes, warnings=warnings
        )
        aliases = {**DEFAULT_TOOL_ALIASES, **(tool_aliases or {})}
        requested = fm.allowed_tools
        if requested is not None:
            mapped = []
            for tool in requested:
                target = aliases.get(tool, tool)
                if target != tool:
                    mapping[tool] = target
                    warnings.append(f"工具 {tool!r} 已映射为 {target!r}")
                mapped.append(target)
            fm.allowed_tools = mapped
        allowed = validate_allowed_tools(fm, registered, default, named)
        fm.allowed_tools = allowed
        scripts = list(fm.scripts)
        if not scripts:
            scripts = sorted(path for path in attachments if path.startswith("scripts/"))
            fm.scripts = scripts
        if scripts:
            warnings.append("技能包含脚本；导入后须信任当前包 hash，且每次执行仍需权限确认")
        status = "degraded" if warnings or scripts else "ready"
        report = SkillValidationReport(
            compatible=True,
            normalized_name=fm.name,
            compatibility_status=status,
            capabilities=SkillCapabilityReport(
                attachments=bool(attachments), scripts=bool(scripts)
            ),
            tool_mapping=mapping,
            normalized_frontmatter=fm.model_dump(),
            warnings=warnings,
        )
        return fm, body, attachments, report
    except (SkillValidationError, UnicodeDecodeError) as exc:
        errors.append(str(exc))
        return None, None, {}, SkillValidationReport(compatible=False, errors=errors)
