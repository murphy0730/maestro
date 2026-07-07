"""MCP 工具包装器。

将 MCP 工具包装为本地工具。
"""

from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, create_model

from ..mcp.manager import MCPManager
from ..mcp.types import MCPTool
from .base import (
    BaseTool,
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)


def create_mcp_tool_wrapper(
    mcp_tool: MCPTool,
    mcp_manager: MCPManager
) -> BaseTool:
    """创建 MCP 工具的包装器。"""
    fields = {}
    properties = mcp_tool.input_schema.get("properties", {})
    required = mcp_tool.input_schema.get("required", [])

    for prop_name, prop_schema in properties.items():
        field_type = str
        if prop_schema.get("type") == "integer":
            field_type = int
        elif prop_schema.get("type") == "number":
            field_type = float
        elif prop_schema.get("type") == "boolean":
            field_type = bool
        elif prop_schema.get("type") == "array":
            field_type = list
        elif prop_schema.get("type") == "object":
            field_type = dict

        field_info = {"description": prop_schema.get("description", "")}
        if prop_name in required:
            fields[prop_name] = (field_type, ...)
        else:
            fields[prop_name] = (Optional[field_type], None)

    DynamicInputSchema = create_model(
        f"{mcp_tool.name.replace('-', '_').replace(' ', '_')}_Input",
        **fields
    )

    fully_qualified_name = f"mcp__{mcp_tool.server_name}__{mcp_tool.name}"

    always_load = mcp_tool.metadata.get("anthropic/alwaysLoad", False)
    should_defer = not always_load

    async def mcp_tool_execute(
        args: BaseModel,
        context: dict,
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult:
        try:
            result = await mcp_manager.call_tool(
                mcp_tool.server_name,
                mcp_tool.name,
                args.model_dump()
            )
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                content=result.get("content"),
                mcp_meta=result.get("_meta")
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=str(e)
            )

    return build_tool(ToolDef(
        name=fully_qualified_name,
        description=mcp_tool.description,
        input_schema=DynamicInputSchema,
        execute=mcp_tool_execute,
        permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
        is_readonly=False,  # Conservative default: assume MCP tools may have side effects
        is_mcp=True,
        mcp_info={"server_name": mcp_tool.server_name, "tool_name": mcp_tool.name},
        should_defer=should_defer,
        always_load=always_load
    ))
