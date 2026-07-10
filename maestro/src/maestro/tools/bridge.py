"""新工具框架 → foundation 工具库桥接。

把 tools/ 框架注册表中的工具注册进 foundation.tools.registry.ToolRegistry，
使技能（allowed_tools）与 ReAct AgentLoop 能按名调用这些工具。

权限语义保持不变：桥接 handler 走框架 ToolManager 的执行管道，
requires_confirm 的工具会被权限门拦截并返回确认信息，而不是直接执行。
"""

import json
import logging
from typing import TYPE_CHECKING, Optional

from ..domain.models import ActionResult
from ..foundation.tools.registry import ToolRegistry as FoundationRegistry
from .base import Tool, ToolPermissionLevel, ToolResultStatus
from .manager import ToolManager
from .registry import ToolRegistry as FrameworkRegistry
from .registry import registry as default_framework_registry

if TYPE_CHECKING:
    from ..foundation.authz import ActionGate

logger = logging.getLogger(__name__)


def _kind_for(tool: Tool) -> str:
    if not tool.is_readonly:
        return "write"
    return "read" if tool.permission_level == ToolPermissionLevel.AUTO else "aux"


def register_framework_tools(
    foundation_registry: FoundationRegistry,
    tool_manager: ToolManager | None = None,
    gate: Optional["ActionGate"] = None,
    framework_tools: FrameworkRegistry | None = None,
) -> list[str]:
    """把框架注册表中所有启用的工具桥接进 foundation 工具库。

    返回实际桥接的工具名列表；与 foundation 已有工具重名时跳过（foundation 优先）。
    传入 gate 时，requires_confirm 工具被拦截后会生成 PendingAction（随 actions
    事件下发前台确认卡片，经 /chat/confirm 批准后真正执行）；不传则仅返回拦截信息。
    """
    framework_tools = framework_tools or default_framework_registry
    manager = tool_manager or ToolManager(registry=framework_tools)
    existing = set(foundation_registry.names())
    bridged: list[str] = []

    for tool in framework_tools.list_enabled():
        if tool.name in existing:
            logger.warning("[BRIDGE] 跳过重名工具: %s (foundation 已注册)", tool.name)
            continue

        def make_handler(tool_name: str, framework_tool: Tool):
            async def handler(**kwargs):
                # The scheduling path has one policy source: PermissionEngine for
                # admission and ActionGate for confirmations.  Do not run the
                # framework's independent PermissionChecker a second time.
                if framework_tool.permission_level == ToolPermissionLevel.DENIED:
                    return {"blocked_by_permission": True, "note": "该工具被策略拒绝"}
                if framework_tool.permission_level == ToolPermissionLevel.REQUIRES_CONFIRM:
                    if gate is None:
                        # Standalone framework use retains its local confirmation
                        # API. The platform path always supplies ActionGate.
                        result = await manager.execute_tool(tool_name, kwargs, context={})
                        return {
                            "blocked_by_permission": True,
                            **(result.content if isinstance(result.content, dict) else {}),
                            "note": "该工具需人工确认",
                        }
                    params_brief = json.dumps(kwargs, ensure_ascii=False, default=str)
                    if len(params_brief) > 200:
                        params_brief = params_brief[:200] + "…"
                    outcome = await gate.request(
                        action_type=f"tool:{tool_name}",
                        description=f"执行工具 {tool_name}，参数: {params_brief}",
                        params=kwargs,
                        executor=_make_direct_executor(manager, tool_name, kwargs),
                    )
                    if outcome.status == "pending" and outcome.action:
                        return {
                            "blocked_by_permission": True,
                            "action_id": outcome.action.action_id,
                            "note": "该工具需人工确认，已生成待确认动作，请在前台确认后执行",
                        }
                    if outcome.status == "denied":
                        return {"blocked_by_permission": True, "note": "该工具被策略拒绝"}
                    return {"executed_via_gate": True, "detail": outcome.result.detail if outcome.result else ""}

                result = await manager.execute_tool(
                    tool_name, kwargs, context={}, skip_permission=True
                )
                if result.status == ToolResultStatus.SUCCESS:
                    return result.content
                if (
                    result.status == ToolResultStatus.CANCELLED
                    and isinstance(result.content, dict)
                    and result.content.get("requires_confirmation")
                ):
                    confirmation_id = result.content.get("confirmation_id")
                    if gate is not None and confirmation_id:
                        params_brief = json.dumps(kwargs, ensure_ascii=False, default=str)
                        if len(params_brief) > 200:
                            params_brief = params_brief[:200] + "…"
                        outcome = await gate.request(
                            action_type=f"tool:{tool_name}",
                            description=f"执行工具 {tool_name}，参数: {params_brief}",
                            params=kwargs,
                            executor=_make_executor(manager, tool_name, confirmation_id),
                        )
                        if outcome.status == "pending" and outcome.action:
                            return {
                                "blocked_by_permission": True,
                                "action_id": outcome.action.action_id,
                                "note": "该工具需人工确认，已生成待确认动作，请在前台确认后执行",
                            }
                        if outcome.status == "denied":
                            return {"blocked_by_permission": True, "note": "该工具被策略拒绝"}
                        # auto (策略放行): executor 已执行
                        detail = outcome.result.detail if outcome.result else ""
                        return {"executed_via_gate": True, "detail": detail}
                    return {
                        "blocked_by_permission": True,
                        **result.content,
                        "note": "该工具被权限门拦截，需人工确认后才会执行，本次未执行任何操作",
                    }
                return {"error": result.error_message or "tool execution failed"}
            return handler

        foundation_registry.register(
            name=tool.name,
            description=tool.description,
            parameters=tool.input_schema.model_json_schema(),
            handler=make_handler(tool.name, tool),
            kind=_kind_for(tool),
            should_defer=tool.should_defer and not tool.always_load,
        )
        bridged.append(tool.name)

    logger.info("[BRIDGE] 桥接工具 %d 个: %s", len(bridged), bridged)
    return bridged


def _make_direct_executor(manager: ToolManager, tool_name: str, kwargs: dict):
    """Run a framework tool after ActionGate has approved it.

    This intentionally bypasses PermissionChecker: ActionGate is the sole
    confirmation owner for bridged tools in the platform request path.
    """

    async def _execute() -> ActionResult:
        result = await manager.execute_tool(
            tool_name, kwargs, context={}, skip_permission=True
        )
        ok = result.status == ToolResultStatus.SUCCESS
        detail = (
            json.dumps(result.content, ensure_ascii=False, default=str)
            if ok
            else result.error_message or "tool execution failed"
        )
        return ActionResult(success=ok, action=f"tool:{tool_name}", detail=detail)

    return _execute
