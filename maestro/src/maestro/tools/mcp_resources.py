"""MCP 资源工具。

提供 list_mcp_resources / read_mcp_resource 两个工具，把 MCP 服务器暴露的
资源（resources）开放给 Agent。迁移自 Claude Code 的 ListMcpResourcesTool /
ReadMcpResourceTool。

工具需要 MCPManager 实例，故以工厂函数创建，由 IntegratedToolManager 注册。
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from ..mcp.manager import MCPManager
from .base import (
    Tool,
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)


class ListMcpResourcesArgs(BaseModel):
    server: Optional[str] = Field(
        default=None, description="Optional server name to filter resources by"
    )


class ReadMcpResourceArgs(BaseModel):
    server: str = Field(description="The MCP server name")
    uri: str = Field(description="The resource URI to read")


def create_mcp_resource_tools(mcp_manager: MCPManager) -> List[Tool]:
    """创建绑定到指定 MCPManager 的资源工具。"""

    async def list_resources_execute(
        args: ListMcpResourcesArgs,
        context: dict,
        on_progress: None = None
    ) -> ToolResult:
        connections = [
            c for c in mcp_manager.get_all_connections() if c.status == "connected"
        ]
        if args.server:
            connections = [c for c in connections if c.name == args.server]
            if not connections:
                available = [c.name for c in mcp_manager.get_all_connections()]
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    content=None,
                    error_message=(
                        f'Server "{args.server}" not found. '
                        f"Available servers: {', '.join(available) or '(none)'}"
                    )
                )

        resources = [
            {
                "uri": r.uri,
                "name": r.name,
                "description": r.description,
                "mime_type": r.mime_type,
                "server": conn.name,
            }
            for conn in connections
            for r in conn.resources
        ]
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"resources": resources, "count": len(resources)}
        )

    async def read_resource_execute(
        args: ReadMcpResourceArgs,
        context: dict,
        on_progress: None = None
    ) -> ToolResult:
        try:
            contents = await mcp_manager.read_resource(args.server, args.uri)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                content={"server": args.server, "uri": args.uri, "contents": contents}
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=str(e)
            )

    list_tool = build_tool(ToolDef(
        name="list_mcp_resources",
        description=(
            "List available resources from connected MCP servers. "
            "Servers may still provide tools even if they have no resources."
        ),
        input_schema=ListMcpResourcesArgs,
        execute=list_resources_execute,
        permission_level=ToolPermissionLevel.AUTO,
        is_readonly=True,
        is_concurrency_safe=True,
        max_result_size_chars=100_000,
        should_defer=True,
        search_hint="list resources from connected MCP servers"
    ))

    read_tool = build_tool(ToolDef(
        name="read_mcp_resource",
        description="Read a specific resource from an MCP server by URI",
        input_schema=ReadMcpResourceArgs,
        execute=read_resource_execute,
        permission_level=ToolPermissionLevel.AUTO,
        is_readonly=True,
        is_concurrency_safe=True,
        max_result_size_chars=100_000,
        should_defer=True,
        search_hint="read a resource from an MCP server"
    ))

    return [list_tool, read_tool]
