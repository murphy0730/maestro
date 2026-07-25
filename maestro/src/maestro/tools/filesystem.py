"""Workspace-confined filesystem primitives.

These are the capabilities `DEFAULT_TOOL_ALIASES` maps Claude's `Read`/`Glob`/
`Grep`/`Write`/`Edit` onto, so a skill declaring ``allowed-tools: [Read]`` has
something real to call.

Every path argument goes through `safe_join` against a single workspace root;
there is no way to name a file outside it.  Reads are low risk and run on the
fast path.  Writes are declared `writes=True, risk=HIGH`, which the Policy Gate
turns into a human approval before anything touches disk.
"""

from __future__ import annotations

import re
from pathlib import Path

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.paths import UnsafePathError, safe_join

_MAX_READ_BYTES = 256 * 1024
_MAX_MATCHES = 200
_MAX_ENTRIES = 500


def _text(call: CapabilityCall, key: str) -> str:
    value = call.arguments.get(key)
    return value if isinstance(value, str) else ""


def _int(call: CapabilityCall, key: str, default: int) -> int:
    value = call.arguments.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _failed(message: str) -> CapabilityResult:
    return CapabilityResult(status="failed", error_message=message)


def register_filesystem_capabilities(registry: CapabilityRegistry, workspace_root: Path) -> None:
    """Register the workspace filesystem primitives into `registry`."""
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)

    def resolve(call: CapabilityCall, key: str = "path") -> Path:
        relative = _text(call, key)
        if not relative:
            raise UnsafePathError(f"缺少必填参数 {key}")
        return safe_join(root, relative)

    async def read_file(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        try:
            target = resolve(call)
        except UnsafePathError as error:
            return _failed(str(error))
        if not target.is_file():
            return _failed(f"文件不存在: {_text(call, 'path')}")
        try:
            content = target.read_text("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return _failed(f"无法读取文件: {error}")
        lines = content.splitlines()
        offset = max(_int(call, "offset", 0), 0)
        limit = _int(call, "limit", 0)
        window = lines[offset : offset + limit] if limit > 0 else lines[offset:]
        text = "\n".join(window)
        truncated = len(text.encode("utf-8")) > _MAX_READ_BYTES
        if truncated:
            text = text.encode("utf-8")[:_MAX_READ_BYTES].decode("utf-8", "ignore")
        return CapabilityResult(
            status="succeeded",
            content={
                "path": _text(call, "path"),
                "content": text,
                "total_lines": len(lines),
                "truncated": truncated,
            },
        )

    async def glob_files(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        pattern = _text(call, "pattern")
        if not pattern:
            return _failed("缺少必填参数 pattern")
        if pattern.startswith("/") or ".." in Path(pattern).parts or "\\" in pattern:
            return _failed(f"unsafe pattern: {pattern!r}")
        base = root.resolve()
        matches = []
        for path in sorted(base.glob(pattern)):
            if not path.is_file() or not path.resolve().is_relative_to(base):
                continue
            matches.append(path.relative_to(base).as_posix())
            if len(matches) >= _MAX_ENTRIES:
                break
        return CapabilityResult(
            status="succeeded",
            content={"pattern": pattern, "matches": matches, "truncated": len(matches) >= _MAX_ENTRIES},
        )

    async def grep_files(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        pattern = _text(call, "pattern")
        if not pattern:
            return _failed("缺少必填参数 pattern")
        try:
            expression = re.compile(pattern)
        except re.error as error:
            return _failed(f"非法正则: {error}")
        relative = _text(call, "path")
        try:
            scope = safe_join(root, relative) if relative else root.resolve()
        except UnsafePathError as error:
            return _failed(str(error))
        candidates = [scope] if scope.is_file() else sorted(p for p in scope.rglob("*") if p.is_file())
        hits: list[dict[str, object]] = []
        for path in candidates:
            try:
                content = path.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(content.splitlines(), start=1):
                if expression.search(line):
                    hits.append(
                        {
                            "path": path.relative_to(root.resolve()).as_posix(),
                            "line": number,
                            "text": line[:500],
                        }
                    )
                    if len(hits) >= _MAX_MATCHES:
                        break
            if len(hits) >= _MAX_MATCHES:
                break
        return CapabilityResult(
            status="succeeded",
            content={"pattern": pattern, "matches": hits, "truncated": len(hits) >= _MAX_MATCHES},
        )

    async def write_file(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        try:
            target = resolve(call)
        except UnsafePathError as error:
            return _failed(str(error))
        content = _text(call, "content")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, "utf-8")
        except OSError as error:
            return _failed(f"无法写入文件: {error}")
        return CapabilityResult(
            status="succeeded",
            content={"path": _text(call, "path"), "bytes": len(content.encode("utf-8"))},
        )

    async def edit_file(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        try:
            target = resolve(call)
        except UnsafePathError as error:
            return _failed(str(error))
        if not target.is_file():
            return _failed(f"文件不存在: {_text(call, 'path')}")
        old = _text(call, "old")
        new = _text(call, "new")
        if not old:
            return _failed("缺少必填参数 old")
        try:
            content = target.read_text("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return _failed(f"无法读取文件: {error}")
        occurrences = content.count(old)
        if occurrences == 0:
            return _failed("old 在文件中不存在")
        if occurrences > 1:
            return _failed(f"old 在文件中出现 {occurrences} 次，必须唯一")
        try:
            target.write_text(content.replace(old, new, 1), "utf-8")
        except OSError as error:
            return _failed(f"无法写入文件: {error}")
        return CapabilityResult(
            status="succeeded", content={"path": _text(call, "path"), "replacements": 1}
        )

    specs = (
        CapabilitySpec(
            name="read_file",
            kind=CapabilityKind.TOOL,
            description="读取工作区内的一个文本文件。参数 path 为相对工作区的路径，可选 offset/limit 按行截取。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
            risk=RiskLevel.LOW,
            executor=read_file,
        ),
        CapabilitySpec(
            name="glob",
            kind=CapabilityKind.TOOL,
            description="按 glob 模式列出工作区内的文件，例如 '**/*.md'。",
            input_schema={
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
            risk=RiskLevel.LOW,
            executor=glob_files,
        ),
        CapabilitySpec(
            name="grep",
            kind=CapabilityKind.TOOL,
            description="在工作区内按正则搜索文件内容。可选 path 限定到某个文件或子目录。",
            input_schema={
                "type": "object",
                "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                "required": ["pattern"],
            },
            risk=RiskLevel.LOW,
            executor=grep_files,
        ),
        CapabilitySpec(
            name="write_file",
            kind=CapabilityKind.TOOL,
            description="把内容写入工作区内的文件（覆盖）。需要人工确认。",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
            risk=RiskLevel.HIGH,
            writes=True,
            idempotent=True,
            executor=write_file,
        ),
        CapabilitySpec(
            name="edit_file",
            kind=CapabilityKind.TOOL,
            description="把工作区文件中唯一出现的 old 替换为 new。需要人工确认。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
                "required": ["path", "old", "new"],
            },
            risk=RiskLevel.HIGH,
            writes=True,
            idempotent=False,
            executor=edit_file,
        ),
    )
    for spec in specs:
        registry.register(spec, replace=True)
