"""集成的工具管理器。

结合内置工具和 MCP 工具的管理器。
"""

from typing import Any, Callable, Dict, List, Optional

from ..mcp.manager import MCPManager
from .base import Tool
from .manager import ToolManager
from .mcp_resources import create_mcp_resource_tools
from .mcp_wrapper import create_mcp_tool_wrapper
from .registry import ToolRegistry, registry as default_registry


class IntegratedToolManager:
    """集成工具管理器，结合内置工具和 MCP 工具。"""

    def __init__(
        self,
        mcp_manager: Optional[MCPManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.registry = tool_registry or default_registry
        self.tool_manager = ToolManager(registry=self.registry)
        self.mcp_manager = mcp_manager or MCPManager()
        self._mcp_tools_registered: List[str] = []
        # MCP 资源工具绑定本管理器的 MCPManager 实例
        for tool in create_mcp_resource_tools(self.mcp_manager):
            self.registry.register(tool)

    async def refresh_mcp_tools(self) -> None:
        """刷新 MCP 工具。"""
        for tool_name in self._mcp_tools_registered:
            try:
                self.registry.unregister(tool_name)
            except Exception:
                pass

        self._mcp_tools_registered = []

        mcp_tools = self.mcp_manager.get_all_tools()
        for mcp_tool in mcp_tools:
            wrapper = create_mcp_tool_wrapper(mcp_tool, self.mcp_manager)
            self.registry.register(wrapper)
            self._mcp_tools_registered.append(wrapper.name)

    def get_tools_for_agent(self) -> List[Dict[str, Any]]:
        """获取 Agent 使用的工具列表。"""
        return self.tool_manager.get_tools_for_agent()

    def get_all_tools_metadata(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据。"""
        return self.tool_manager.get_all_tools_metadata()

    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ):
        """执行工具。"""
        return await self.tool_manager.execute_tool(
            tool_name, args, context, on_progress
        )

    async def confirm_execution(
        self,
        confirmation_id: str,
        approved: bool,
        on_progress: Optional[Callable[[Any], None]] = None
    ):
        """确认执行。"""
        return await self.tool_manager.confirm_execution(
            confirmation_id, approved, on_progress
        )

    def get_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        """获取待确认的执行。"""
        return self.tool_manager.get_pending_confirmations()

    def assemble_tool_pool(self) -> List[Tool]:
        """组装完整的工具池。"""
        mcp_tools = []
        for conn in self.mcp_manager.get_all_connections():
            if conn.status == "connected":
                for mcp_tool in conn.tools:
                    try:
                        wrapper = create_mcp_tool_wrapper(mcp_tool, self.mcp_manager)
                        mcp_tools.append(wrapper)
                    except Exception:
                        pass

        return self.tool_manager.assemble_tool_pool(mcp_tools)
