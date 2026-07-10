from __future__ import annotations
import io
import zipfile
from pathlib import Path
import yaml
from pydantic import ValidationError
from maestro.skills.schemas import SkillFrontmatter, SkillValidationError

_BODY_MAX = 32 * 1024
_ZIP_MAX_MEMBERS = 50
_ZIP_MAX_TOTAL = 10 * 1024 * 1024


def parse_skill_md(text: str, max_bytes: int = _BODY_MAX) -> tuple[SkillFrontmatter, str]:
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
    data: bytes, filename: str, max_bytes: int = _BODY_MAX
) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    name = filename.lower()
    if name.endswith(".md"):
        fm, body = parse_skill_md(data.decode("utf-8"), max_bytes)
        return fm, body, {}
    if name.endswith(".zip"):
        return _extract_zip(data, max_bytes)
    raise SkillValidationError("仅支持 .md / .zip 后缀")


def _extract_zip(
    data: bytes, max_bytes: int = _BODY_MAX
) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    bio = io.BytesIO(data)
    try:
        zf = zipfile.ZipFile(bio)
    except zipfile.BadZipFile as e:
        raise SkillValidationError(f"zip 解压失败: {e}") from e
    members = [i for i in zf.infolist() if not i.is_dir()]
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
    fm, body = parse_skill_md(files[skill_path].decode("utf-8"), max_bytes)
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
