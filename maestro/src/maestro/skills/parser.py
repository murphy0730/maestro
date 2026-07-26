from __future__ import annotations
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
from pydantic import ValidationError
from maestro.skills.schemas import (
    SkillCapabilityReport,
    RuntimeSkillFrontmatter,
    SkillValidationError,
    SkillValidationReport,
)

_BODY_MAX = 32 * 1024
_ZIP_MAX_MEMBERS = 200
_ZIP_MAX_TOTAL = 10 * 1024 * 1024
_IGNORED_PACKAGE_PARTS = {".DS_Store", "__MACOSX"}

RUNTIME_FIELD_ALIASES = {
    "allowed-tools": "allowed_tools",
    "argument-hint": "argument_hint",
    "user-invocable": "user_invocable",
    "disable-model-invocation": "disable_model_invocation",
}
RUNTIME_KNOWN_FIELDS = set(RuntimeSkillFrontmatter.model_fields) - {"extensions"}
# Claude tool names mapped onto this host's capabilities.  Only map a name the
# host actually registers: an alias pointing at nothing turns every skill that
# declares it into a discovery failure, and hides why.  `PowerShell`, `WebFetch`
# and `TodoWrite` have no counterpart here — a host that wants them registers the
# capability and adds the alias with it.
DEFAULT_TOOL_ALIASES = {
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "edit_file",
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
}


@dataclass(frozen=True)
class ExtractedSkill:
    """A parsed skill package, ready to be written to disk or inspected."""

    frontmatter: RuntimeSkillFrontmatter
    text: str
    body: str
    attachments: dict[str, bytes] = field(default_factory=dict)
    archive_bytes: int | None = None


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a SKILL.md into its raw frontmatter block and its body."""
    if not text.startswith("---"):
        raise SkillValidationError("frontmatter 必须以 '---' 开头")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillValidationError("frontmatter 缺少结束 '---'")
    return parts[1], parts[2].lstrip("\n")


def parse_runtime_frontmatter(text: str) -> RuntimeSkillFrontmatter:
    """Parse the Runtime's strict Claude-compatible metadata contract.

    Unknown keys are retained as inert extensions rather than being treated as
    legacy SkillEngine execution semantics.
    """
    raw, _body = split_frontmatter(text)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise SkillValidationError(f"frontmatter YAML 解析失败: {error}") from error
    if not isinstance(data, dict):
        raise SkillValidationError("frontmatter 必须解析为 dict")
    normalized: dict[str, Any] = {}
    extensions: dict[str, Any] = {}
    for raw_key, value in data.items():
        key = RUNTIME_FIELD_ALIASES.get(str(raw_key), str(raw_key))
        if key in RUNTIME_KNOWN_FIELDS:
            normalized[key] = value
        else:
            extensions[str(raw_key)] = value
    allowed = normalized.get("allowed_tools")
    if isinstance(allowed, str):
        normalized["allowed_tools"] = [part for part in re.split(r"[\s,]+", allowed) if part]
    if extensions:
        normalized["extensions"] = extensions
    try:
        return RuntimeSkillFrontmatter(**normalized)
    except ValidationError as error:
        raise SkillValidationError(str(error)) from error


def extract_package(
    data: bytes, filename: str, max_bytes: int = _BODY_MAX
) -> ExtractedSkill:
    """Safely unpack a `.md` / `.zip` skill package under the Runtime contract."""
    name = filename.lower()
    if name.endswith(".md"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SkillValidationError(f"SKILL.md 不是合法 UTF-8: {error}") from error
        return _build(text, {}, max_bytes, archive_bytes=None)
    if name.endswith(".zip"):
        text, attachments = _extract_zip(data)
        return _build(text, attachments, max_bytes, archive_bytes=len(data))
    raise SkillValidationError("仅支持 .md / .zip 后缀")


def _build(
    text: str, attachments: dict[str, bytes], max_bytes: int, *, archive_bytes: int | None
) -> ExtractedSkill:
    frontmatter = parse_runtime_frontmatter(text)
    _raw, body = split_frontmatter(text)
    if not body.strip():
        raise SkillValidationError("正文不能为空")
    if len(body.encode("utf-8")) > max_bytes:
        raise SkillValidationError(f"正文需 ≤{max_bytes // 1024}KB")
    return ExtractedSkill(
        frontmatter=frontmatter,
        text=text,
        body=body,
        attachments=attachments,
        archive_bytes=archive_bytes,
    )


def _extract_zip(data: bytes) -> tuple[str, dict[str, bytes]]:
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
    try:
        text = files[skill_path].decode("utf-8")
    except UnicodeDecodeError as error:
        raise SkillValidationError(f"SKILL.md 不是合法 UTF-8: {error}") from error
    return text, attachments


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


def map_allowed_tools(
    requested: list[str] | None, aliases: dict[str, str] | None = None
) -> tuple[list[str], dict[str, str], list[str]]:
    """Map Claude tool names onto Runtime capability names.

    Returns the mapped names, the applied mapping and a warning per rename so
    callers can show the user what a package will actually be granted.
    """
    table = {**DEFAULT_TOOL_ALIASES, **(aliases or {})}
    mapping: dict[str, str] = {}
    warnings: list[str] = []
    mapped: list[str] = []
    for tool in requested or []:
        target = table.get(tool, tool)
        if target != tool:
            mapping[tool] = target
            warnings.append(f"工具 {tool!r} 已映射为 {target!r}")
        mapped.append(target)
    return mapped, mapping, warnings


def validate_runtime_package(
    data: bytes,
    filename: str,
    registered: set[str],
    max_bytes: int = _BODY_MAX,
    tool_aliases: dict[str, str] | None = None,
) -> tuple[ExtractedSkill | None, SkillValidationReport]:
    """Preflight a package against the live capability registry.

    This is the single validation path shared by `POST /skills/validate` and
    `POST /skills/import`, so a package can never be imported under looser
    rules than the ones the user was shown.
    """
    try:
        package = extract_package(data, filename, max_bytes)
    except (SkillValidationError, UnicodeDecodeError, ValueError) as error:
        return None, SkillValidationReport(
            compatible=False, compatibility_status="not_ready", errors=[str(error)]
        )

    mapped, mapping, warnings = map_allowed_tools(
        package.frontmatter.allowed_tools, tool_aliases
    )
    unknown = [name for name in mapped if name not in registered]
    if unknown:
        return None, SkillValidationReport(
            compatible=False,
            normalized_name=package.frontmatter.name,
            compatibility_status="not_ready",
            tool_mapping=mapping,
            warnings=warnings,
            errors=[f"allowed-tools contains unknown capability: {unknown}"],
        )

    scripts = sorted(path for path in package.attachments if path.startswith("scripts/"))
    if scripts:
        warnings.append("技能包含脚本；导入后须信任当前包 hash，且每次执行仍需人工确认")
    report = SkillValidationReport(
        compatible=True,
        normalized_name=package.frontmatter.name,
        compatibility_status="degraded" if warnings else "ready",
        capabilities=SkillCapabilityReport(
            attachments=bool(package.attachments), scripts=bool(scripts)
        ),
        tool_mapping=mapping,
        normalized_frontmatter=package.frontmatter.model_dump(),
        warnings=warnings,
    )
    return package, report
