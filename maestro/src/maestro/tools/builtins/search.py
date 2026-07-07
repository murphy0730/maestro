"""搜索工具。

提供 grep / glob 工具用于在文件中搜索模式或按通配符匹配文件。
所有文件操作限制在项目根目录内。
"""

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from maestro.config import project_root

from ..base import (
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)


def _resolve_and_validate_path(path_str: str) -> Path:
    """解析并验证路径在项目根目录内。"""
    root = project_root()
    path = (root / path_str).resolve()
    
    if not path.is_relative_to(root):
        raise ValueError(f"Path '{path_str}' escapes project root directory")
    
    return path


class GrepArgs(BaseModel):
    pattern: str = Field(description="Pattern to search for")
    directory: Optional[str] = Field(default=".", description="Directory to search in (relative to project root)")


async def grep_execute(
    args: GrepArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        dir_path = _resolve_and_validate_path(args.directory)
        if not dir_path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Directory not found: {args.directory}"
            )
        
        # Compile pattern once outside the loop
        try:
            pattern_re = re.compile(args.pattern)
        except re.error as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Invalid regex pattern: {e}"
            )

        results = []
        for file_path in dir_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                try:
                    content = file_path.read_text(encoding='utf-8')
                    for line_num, line in enumerate(content.split('\n'), 1):
                        if pattern_re.search(line):
                            results.append({
                                "file": str(file_path.relative_to(project_root())),
                                "line": line_num,
                                "content": line.strip()
                            })
                            if len(results) >= 100:
                                break
                except (UnicodeDecodeError, PermissionError):
                    continue
            if len(results) >= 100:
                break

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"pattern": args.pattern, "matches": results, "count": len(results)}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


GrepTool = build_tool(ToolDef(
    name="grep",
    description="Search for a pattern in files (directory relative to project root)",
    input_schema=GrepArgs,
    execute=grep_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    search_hint="search pattern find grep"
))


class GlobArgs(BaseModel):
    pattern: str = Field(description="Glob pattern to match files against, e.g. '**/*.py' or 'src/*.md'")
    path: Optional[str] = Field(default=".", description="Directory to search in (relative to project root)")


async def glob_execute(
    args: GlobArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        base_dir = _resolve_and_validate_path(args.path)
        if not base_dir.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Directory not found: {args.path}"
            )
        if not base_dir.is_dir():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Path is not a directory: {args.path}"
            )
        if args.pattern.startswith(("/", "~")):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message="Pattern must be relative, not absolute"
            )

        matched = [p for p in base_dir.glob(args.pattern) if p.is_file()]
        # 与参考实现一致: 按修改时间倒序，最多返回 100 条并标记截断
        matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        truncated = len(matched) > 100
        filenames = [str(p.relative_to(project_root())) for p in matched[:100]]

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={
                "pattern": args.pattern,
                "filenames": filenames,
                "num_files": len(filenames),
                "truncated": truncated,
            }
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


GlobTool = build_tool(ToolDef(
    name="glob",
    description="Find files by name pattern or wildcard (paths relative to project root, sorted by modification time)",
    input_schema=GlobArgs,
    execute=glob_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    max_result_size_chars=100_000,
    search_hint="find files by name pattern or wildcard"
))


def register_search_tools():
    from ..registry import registry
    registry.register(GrepTool)
    registry.register(GlobTool)
