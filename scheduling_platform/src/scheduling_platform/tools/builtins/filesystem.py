"""文件系统工具。

提供 read_file, write_file, edit_file, list_files 等工具。
所有文件操作限制在项目根目录内。
"""

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from scheduling_platform.config import project_root

from ..base import (
    BaseTool,
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


class ReadFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to project root)")
    offset: Optional[int] = Field(default=None, description="Start reading from this line number")
    limit: Optional[int] = Field(default=None, description="Maximum number of lines to read")


async def read_file_execute(
    args: ReadFileArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = _resolve_and_validate_path(args.file_path)
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"File not found: {args.file_path}"
            )

        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')

        if args.offset is not None and args.offset > 0:
            lines = lines[args.offset-1:]
        if args.limit is not None and args.limit > 0:
            lines = lines[:args.limit]

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content='\n'.join(lines)
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


ReadFileTool = build_tool(ToolDef(
    name="read_file",
    description="Read the contents of a file (path relative to project root)",
    input_schema=ReadFileArgs,
    execute=read_file_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    max_result_size_chars=float('inf'),
    search_hint="file contents read"
))


class WriteFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to write (relative to project root)")
    content: str = Field(description="Content to write to the file")


async def write_file_execute(
    args: WriteFileArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = _resolve_and_validate_path(args.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding='utf-8')
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"file_path": args.file_path, "bytes_written": len(args.content)}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


WriteFileTool = build_tool(ToolDef(
    name="write_file",
    description="Write content to a file (path relative to project root)",
    input_schema=WriteFileArgs,
    execute=write_file_execute,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=True,
    search_hint="file write save"
))


class EditFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to edit (relative to project root)")
    old_string: str = Field(description="Exact string to replace")
    new_string: str = Field(description="Replacement string")


async def edit_file_execute(
    args: EditFileArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = _resolve_and_validate_path(args.file_path)
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"File not found: {args.file_path}"
            )

        content = path.read_text(encoding='utf-8')
        if args.old_string not in content:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message="Old string not found in file"
            )

        new_content = content.replace(args.old_string, args.new_string)
        path.write_text(new_content, encoding='utf-8')

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"file_path": args.file_path, "replaced": True}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


EditFileTool = build_tool(ToolDef(
    name="edit_file",
    description="Edit a file by replacing an exact string (path relative to project root)",
    input_schema=EditFileArgs,
    execute=edit_file_execute,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=True,
    search_hint="file edit modify replace"
))


class ListFilesArgs(BaseModel):
    directory: str = Field(default=".", description="Directory to list files from (relative to project root)")


async def list_files_execute(
    args: ListFilesArgs,
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

        files = []
        for item in sorted(dir_path.iterdir()):
            files.append({
                "name": item.name,
                "path": str(item.relative_to(project_root())),
                "is_dir": item.is_dir(),
                "is_file": item.is_file(),
                "size": item.stat().st_size if item.is_file() else None
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"directory": args.directory, "files": files}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


ListFilesTool = build_tool(ToolDef(
    name="list_files",
    description="List files and directories in a given directory (path relative to project root)",
    input_schema=ListFilesArgs,
    execute=list_files_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    search_hint="directory list ls"
))


def register_filesystem_tools():
    from ..registry import registry
    registry.register(ReadFileTool)
    registry.register(WriteFileTool)
    registry.register(EditFileTool)
    registry.register(ListFilesTool)
