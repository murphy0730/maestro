"""等待工具。

提供 sleep 工具，供 Agent 在轮询外部状态（如等待任务令状态刷新）时定时等待。
迁移自 Claude Code 的 SleepTool，上限 300 秒防止挂死循环。
"""

import asyncio

from pydantic import BaseModel, Field

from ..base import (
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)

MAX_SLEEP_SECONDS = 300.0


class SleepArgs(BaseModel):
    seconds: float = Field(gt=0, le=MAX_SLEEP_SECONDS, description="Seconds to sleep (max 300)")


async def sleep_execute(
    args: SleepArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    await asyncio.sleep(args.seconds)
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        content={"slept_seconds": args.seconds}
    )


SleepTool = build_tool(ToolDef(
    name="sleep",
    description="Sleep for a given number of seconds (max 300), for polling external state",
    input_schema=SleepArgs,
    execute=sleep_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    should_defer=True,
    search_hint="sleep wait delay poll"
))


def register_sleep_tools():
    from ..registry import registry
    registry.register(SleepTool)
