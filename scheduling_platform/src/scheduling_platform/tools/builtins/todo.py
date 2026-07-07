"""任务清单工具。

提供 todo_write 工具，供 Agent 在多步任务中维护会话级任务清单。
迁移自 Claude Code 的 TodoWriteTool：清单按会话/Agent 分键存于进程内，
全部完成时自动清空。
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..base import (
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)

# 进程内清单存储: key = agent_id 或 session_id (缺省 "default")
_todo_store: Dict[str, List[dict]] = {}


class TodoItem(BaseModel):
    content: str = Field(description="Task description")
    status: Literal["pending", "in_progress", "completed"] = Field(
        description="Task status"
    )
    active_form: Optional[str] = Field(
        default=None, description="Present-tense form shown while in progress"
    )


class TodoWriteArgs(BaseModel):
    todos: List[TodoItem] = Field(description="The updated todo list")


def _todo_key(context: dict) -> str:
    return context.get("agent_id") or context.get("session_id") or "default"


def get_todos(context: dict) -> List[dict]:
    """读取当前会话的任务清单（供 Agent 循环 / UI 使用）。"""
    return list(_todo_store.get(_todo_key(context), []))


async def todo_write_execute(
    args: TodoWriteArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    key = _todo_key(context)
    old_todos = _todo_store.get(key, [])
    new_todos = [t.model_dump() for t in args.todos]

    # 与参考实现一致: 全部完成视为任务结束，清空存储
    all_done = bool(new_todos) and all(t["status"] == "completed" for t in new_todos)
    _todo_store[key] = [] if all_done else new_todos

    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        content={
            "old_todos": old_todos,
            "new_todos": new_todos,
            "message": (
                "Todos have been modified successfully. Ensure that you continue "
                "to use the todo list to track your progress."
            ),
        }
    )


TodoWriteTool = build_tool(ToolDef(
    name="todo_write",
    description="Create and update the session task checklist to track progress on multi-step work",
    input_schema=TodoWriteArgs,
    execute=todo_write_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    max_result_size_chars=100_000,
    search_hint="manage the session task checklist todo"
))


def register_todo_tools():
    from ..registry import registry
    registry.register(TodoWriteTool)
