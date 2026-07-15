from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from maestro.runtime.capabilities import CapabilitySnapshot
from maestro.skills.parser import DEFAULT_TOOL_ALIASES, parse_runtime_frontmatter
from maestro.skills.schemas import RuntimeSkillFrontmatter, SkillValidationError

_SOURCE_PRECEDENCE = ("managed", "user", "project", "additional", "plugin", "bundled", "mcp")
_FRONTMATTER_BYTES = 16 * 1024


class SkillResourceError(ValueError):
    pass


class RemoteSkillExecutionDenied(SkillValidationError):
    pass


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    allowed_tools: tuple[str, ...]
    argument_hint: str | None
    user_invocable: bool
    disable_model_invocation: bool
    context: str
    agent: str | None
    model: str | None
    effort: str | None
    hooks: dict[str, object]
    extensions: dict[str, object]
    source: str
    path: Path
    active: bool = True


@dataclass(frozen=True)
class LoadedSkill:
    metadata: SkillMetadata
    prompt: str
    mode: str


class SkillCatalog:
    """Read-only Runtime skill discovery with bounded metadata loading."""

    def __init__(self, sources: Mapping[str, Path], capabilities: CapabilitySnapshot) -> None:
        unknown = set(sources) - set(_SOURCE_PRECEDENCE)
        if unknown:
            raise ValueError(f"unknown skill sources: {sorted(unknown)}")
        self._sources = {source: Path(path) for source, path in sources.items()}
        self._capabilities = capabilities
        self.io_log: list[str] = []
        self.inactive: list[SkillMetadata] = []
        self._active: dict[str, SkillMetadata] = {}

    def discover(self) -> dict[str, SkillMetadata]:
        selected: dict[str, SkillMetadata] = {}
        inactive: list[SkillMetadata] = []
        for source in _SOURCE_PRECEDENCE:
            root = self._sources.get(source)
            if root is None or not root.exists():
                continue
            for path in self._skill_files(root):
                metadata = self._read_metadata(source, root, path)
                if metadata.name in selected:
                    inactive.append(replace(metadata, active=False))
                else:
                    selected[metadata.name] = metadata
        self._active = selected
        self.inactive = inactive
        return dict(selected)

    def load(self, name: str, *, arguments: str = "", session_id: str = "") -> LoadedSkill:
        metadata = self._active.get(name) or self._find_by_directory_name(name)
        if metadata is None:
            raise KeyError(name)
        text = metadata.path.read_text("utf-8")
        self.io_log.append(f"{metadata.path.parent.name}/SKILL.md:full")
        frontmatter = parse_runtime_frontmatter(text)
        metadata = self._metadata_from(frontmatter, metadata.source, metadata.path)
        _, body = text.split("---", 2)[1:]
        prompt = body.lstrip("\n")
        prompt = prompt.replace("$ARGUMENTS", arguments)
        prompt = prompt.replace("${CLAUDE_SKILL_DIR}", str(metadata.path.parent))
        prompt = prompt.replace("${CLAUDE_SESSION_ID}", session_id)
        return LoadedSkill(metadata=metadata, prompt=prompt, mode=metadata.context)

    def read_resource(self, skill_name: str, resource: str) -> str:
        metadata = self._active.get(skill_name) or self._find_by_directory_name(skill_name)
        if metadata is None:
            raise KeyError(skill_name)
        if not resource or Path(resource).is_absolute() or "\\" in resource:
            raise SkillResourceError(f"unsafe skill resource: {resource!r}")
        if any(ord(char) < 32 for char in resource) or ".." in Path(resource).parts:
            raise SkillResourceError(f"unsafe skill resource: {resource!r}")
        root = metadata.path.parent.resolve()
        target = (root / resource).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise SkillResourceError(f"skill resource not found: {resource}")
        self.io_log.append(f"{metadata.path.parent.name}/{resource}:resource")
        return target.read_text("utf-8")

    @staticmethod
    def _skill_files(root: Path) -> tuple[Path, ...]:
        direct = root / "SKILL.md"
        if direct.is_file():
            return (direct,)
        return tuple(sorted(root.rglob("SKILL.md")))

    def _read_metadata(self, source: str, root: Path, path: Path) -> SkillMetadata:
        with path.open("rb") as handle:
            header = b""
            while len(header) <= _FRONTMATTER_BYTES:
                chunk = handle.read(min(1024, _FRONTMATTER_BYTES + 1 - len(header)))
                if not chunk:
                    break
                header += chunk
                end = header.find(b"\n---\n", 4)
                if end >= 0:
                    header = header[: end + len(b"\n---\n")]
                    break
        if b"\n---\n" not in header[4:]:
            raise SkillValidationError("runtime skill frontmatter exceeds 16KB")
        text = header.decode("utf-8")
        self.io_log.append(f"{path.parent.name}/SKILL.md:frontmatter")
        frontmatter = parse_runtime_frontmatter(text)
        return self._metadata_from(frontmatter, source, path)

    def _metadata_from(
        self, frontmatter: RuntimeSkillFrontmatter, source: str, path: Path
    ) -> SkillMetadata:
        if source == "mcp" and frontmatter.shell is not None:
            raise RemoteSkillExecutionDenied("remote MCP skills may not declare inline shell")
        allowed = []
        for requested in frontmatter.allowed_tools or []:
            name = DEFAULT_TOOL_ALIASES.get(requested, requested)
            try:
                self._capabilities.require(name)
            except KeyError as error:
                raise SkillValidationError(f"allowed-tools contains unknown capability: {requested}") from error
            allowed.append(name)
        return SkillMetadata(
            name=frontmatter.name,
            description=frontmatter.description,
            allowed_tools=tuple(allowed),
            argument_hint=frontmatter.argument_hint,
            user_invocable=frontmatter.user_invocable,
            disable_model_invocation=frontmatter.disable_model_invocation,
            context=frontmatter.context,
            agent=frontmatter.agent,
            model=frontmatter.model,
            effort=frontmatter.effort,
            hooks=frontmatter.hooks,
            extensions=frontmatter.extensions,
            source=source,
            path=path,
        )

    def _find_by_directory_name(self, name: str) -> SkillMetadata | None:
        for source in _SOURCE_PRECEDENCE:
            root = self._sources.get(source)
            if root is None:
                continue
            candidate = root / name / "SKILL.md"
            if not candidate.is_file() and root.name == name:
                candidate = root / "SKILL.md"
            if candidate.is_file():
                frontmatter = parse_runtime_frontmatter(candidate.read_text("utf-8"))
                metadata = self._metadata_from(frontmatter, source, candidate)
                if metadata.name == name:
                    return metadata
        return None
