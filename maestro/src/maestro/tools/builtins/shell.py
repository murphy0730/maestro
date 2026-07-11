import functools
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from maestro.config import Settings, project_root
from maestro.execution.output_store import FileOutputStore
from maestro.execution.service import ShellExecutionService

from ..base import ToolDef, ToolPermissionLevel, ToolResult, ToolResultStatus, build_tool


class ShellArgs(BaseModel):
    command: str = Field(min_length=1, max_length=32768)
    cwd: str = Field(default=".", description="项目根目录内的工作目录")
    timeout_ms: int = Field(default=120000, ge=1, le=1800000)
    description: str | None = Field(default=None, max_length=500)


class ReadOutputArgs(BaseModel):
    ref: str
    stream: Literal["stdout", "stderr"] = "stdout"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=8192, ge=1, le=65536)


@functools.lru_cache(maxsize=1)
def _runtime() -> tuple[ShellExecutionService, FileOutputStore]:
    # 进程内单例: 避免每次工具调用都重解析 Settings、重建 store/service 和
    # 重新发现 srt 二进制 (原先每步 ReAct 都在 async 循环里做这些同步开销)。
    settings = Settings()
    store = FileOutputStore(
        settings.execution_output_dir,
        inline_max_bytes=settings.react_observation_max_bytes,
    )
    service = ShellExecutionService(
        store,
        [project_root()],
        protected_paths=[
            project_root() / ".env",
            project_root() / ".claude",
            settings.skills_dir,
            settings.audit_log_file.parent if settings.audit_log_file else settings.execution_output_dir,
        ],
    )
    return service, store


async def _execute_shell(shell: str, args: ShellArgs, authorized: bool, on_progress=None) -> ToolResult:
    service, _ = _runtime()
    result = await service.execute(
        command=args.command,
        shell=shell,
        cwd=project_root() / Path(args.cwd),
        timeout_ms=args.timeout_ms,
        session_id="agent",
        authorized=authorized,
        on_progress=on_progress,
    )
    status = ToolResultStatus.ERROR if result["status"] in ("failed", "blocked") else ToolResultStatus.SUCCESS
    return ToolResult(status=status, content=result, error_message=result.get("risk", {}).get("reason") if status == ToolResultStatus.ERROR else None)


async def bash_execute(args: ShellArgs, context: dict, on_progress=None) -> ToolResult:
    return await _execute_shell("bash", args, bool(context.get("shell_authorized")), on_progress)


async def powershell_execute(args: ShellArgs, context: dict, on_progress=None) -> ToolResult:
    return await _execute_shell("powershell", args, bool(context.get("shell_authorized")), on_progress)


async def read_output_execute(args: ReadOutputArgs, context: dict, on_progress=None) -> ToolResult:
    _, store = _runtime()
    try:
        content = store.read(args.ref, "agent", args.stream, args.offset, args.limit)
    except (FileNotFoundError, ValueError, PermissionError) as error:
        return ToolResult(ToolResultStatus.ERROR, None, str(error))
    return ToolResult(ToolResultStatus.SUCCESS, content)


def _shell_tool(name: str, execute):
    from maestro.execution.risk import classify_command

    return build_tool(ToolDef(
        name=name,
        description=(
            f"Execute a {name} command using the platform security mode. "
            "Windows uses guarded execution; supported macOS/Linux deployments may use SRT."
        ),
        input_schema=ShellArgs,
        execute=execute,
        permission_level=ToolPermissionLevel.AUTO,
        is_readonly=False,
        is_destructive=True,
        should_defer=True,
        search_hint=f"execute code command script shell {name}",
        risk_classifier=lambda kwargs, shell=name: classify_command(
            str(kwargs.get("command", "")), shell
        ),
    ))


BashTool = _shell_tool("bash", bash_execute)
PowerShellTool = _shell_tool("powershell", powershell_execute)
ReadOutputTool = build_tool(ToolDef(
    name="read_output",
    description="Read a bounded page from stdout or stderr using an opaque output reference.",
    input_schema=ReadOutputArgs,
    execute=read_output_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    search_hint="read command output stdout stderr reference",
))


def register_shell_tools(tool_registry=None):
    from ..registry import registry
    target = tool_registry or registry
    target.register(BashTool)
    target.register(PowerShellTool)
    target.register(ReadOutputTool)
