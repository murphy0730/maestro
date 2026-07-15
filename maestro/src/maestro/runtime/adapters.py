from __future__ import annotations

from typing import Any

from maestro.mcp.manager import MCPManager
from maestro.mcp.types import MCPTool
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.models import RuntimeErrorKind
from maestro.tools.base import BaseTool, ToolResult, ToolResultStatus


def _result_from_tool(result: ToolResult) -> CapabilityResult:
    if result.status is ToolResultStatus.SUCCESS:
        return CapabilityResult(status="succeeded", content=result.content)
    return CapabilityResult(
        status="failed",
        content=result.content,
        error_kind=RuntimeErrorKind.UNKNOWN_OR_BUG,
        error_message=result.error_message,
    )


def tool_to_capability(tool: BaseTool) -> CapabilitySpec:
    """Adapt an existing Tool without making an authorization decision."""

    writes = not tool.is_readonly
    risk = RiskLevel.LOW if tool.is_readonly else (
        RiskLevel.HIGH if tool.is_destructive else RiskLevel.MEDIUM
    )

    async def execute(call: CapabilityCall, idempotency_key: str | None) -> CapabilityResult:
        args = tool.input_schema.model_validate(call.arguments)
        result = await tool.execute(args, {"idempotency_key": idempotency_key})
        return _result_from_tool(result)

    return CapabilitySpec(
        name=tool.name,
        kind=CapabilityKind.TOOL,
        description=tool.description,
        input_schema=tool.input_schema.model_json_schema(),
        risk=risk,
        writes=writes,
        idempotent=not writes,
        executor=execute,
    )


def _registration(manager: MCPManager, server_name: str, tool_name: str) -> dict[str, Any]:
    registrations = getattr(manager, "capability_registrations", {})
    return dict(registrations.get((server_name, tool_name), {}))


def mcp_tool_to_capability(
    server_name: str, tool: MCPTool, manager: MCPManager
) -> CapabilitySpec:
    """Adapt MCP transport results using locally registered risk metadata only."""

    registration = _registration(manager, server_name, tool.name)
    writes = bool(registration.get("writes", False))
    risk = registration.get("risk", RiskLevel.HIGH if writes else RiskLevel.LOW)
    if not isinstance(risk, RiskLevel):
        risk = RiskLevel(risk)

    async def execute(call: CapabilityCall, idempotency_key: str | None) -> CapabilityResult:
        try:
            result = await manager.call_tool(server_name, tool.name, call.arguments)
        except (TimeoutError, ConnectionError) as error:
            return CapabilityResult(
                status="unknown" if writes else "failed",
                error_kind=RuntimeErrorKind.UNKNOWN_OR_BUG,
                error_message=str(error),
            )
        except Exception as error:
            return CapabilityResult(
                status="failed",
                error_kind=RuntimeErrorKind.UNKNOWN_OR_BUG,
                error_message=str(error),
            )
        content = result.get("content") if isinstance(result, dict) else result
        return CapabilityResult(status="succeeded", content=content)

    return CapabilitySpec(
        name=f"mcp__{server_name}__{tool.name}",
        kind=CapabilityKind.MCP,
        description=tool.description,
        input_schema=dict(tool.input_schema),
        risk=risk,
        writes=writes,
        idempotent=bool(registration.get("idempotent", not writes)),
        executor=execute,
    )
