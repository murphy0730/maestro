"""MCP 管理器。

管理多个 MCP 服务器的连接和工具调用。
"""

from typing import Any, Callable, Dict, List, Optional

from .client import MCPClient
from .types import (
    MCPServerConfig,
    MCPServerConnection,
    MCPConfigScope,
    MCPTool,
)


class McpManagerEvents:
    """MCP 管理器事件。"""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {
            "connected": [],
            "disconnected": [],
            "tools_changed": [],
            "error": [],
            "auth_required": []
        }

    def on(self, event: str, handler: Callable) -> None:
        """注册事件处理程序。"""
        if event in self._handlers:
            self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable) -> None:
        """注销事件处理程序。"""
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)

    def emit(self, event: str, *args, **kwargs) -> None:
        """触发事件。"""
        if event in self._handlers:
            for handler in self._handlers[event]:
                try:
                    handler(*args, **kwargs)
                except Exception:
                    pass


class MCPManager:
    """MCP 管理器。"""

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._connections: Dict[str, MCPServerConnection] = {}
        self._events = McpManagerEvents()

    @property
    def events(self) -> McpManagerEvents:
        """获取事件管理器。"""
        return self._events

    async def add_server(self, config: MCPServerConfig) -> None:
        """添加 MCP 服务器配置。"""
        if config.name in self._clients:
            await self.remove_server(config.name)

        client = MCPClient(config)
        self._clients[config.name] = client

    async def connect_server(self, name: str) -> Optional[MCPServerConnection]:
        """连接到 MCP 服务器。"""
        if name not in self._clients:
            return None

        client = self._clients[name]
        try:
            connection = await client.connect()
            self._connections[name] = connection

            if connection.status == "connected":
                self._events.emit("connected", name)
                self._events.emit("tools_changed", name, connection.tools)
            elif connection.status == "needs_auth":
                self._events.emit("auth_required", name)

            return connection
        except Exception as e:
            self._events.emit("error", name, e)
            return None

    async def remove_server(self, name: str) -> None:
        """移除 MCP 服务器。"""
        if name in self._clients:
            await self._clients[name].disconnect()
            del self._clients[name]

        if name in self._connections:
            del self._connections[name]

        self._events.emit("disconnected", name)

    async def connect_all(self) -> List[MCPServerConnection]:
        """连接所有 MCP 服务器。"""
        connections = []
        for name in self._clients:
            conn = await self.connect_server(name)
            if conn:
                connections.append(conn)
        return connections

    async def disconnect_all(self) -> None:
        """断开所有 MCP 服务器。"""
        for name in list(self._clients.keys()):
            await self.remove_server(name)

    def get_connection(self, name: str) -> Optional[MCPServerConnection]:
        """获取服务器连接状态。"""
        return self._connections.get(name)

    def get_all_connections(self) -> List[MCPServerConnection]:
        """获取所有连接。"""
        return list(self._connections.values())

    def get_all_tools(self) -> List[MCPTool]:
        """获取所有连接服务器的工具。"""
        tools = []
        for conn in self._connections.values():
            if conn.status == "connected":
                tools.extend(conn.tools)
        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict
    ) -> Any:
        """调用 MCP 工具。"""
        if server_name not in self._clients:
            raise RuntimeError(f"Server not found: {server_name}")

        client = self._clients[server_name]
        return await client.call_tool(tool_name, arguments)

    async def read_resource(
        self,
        server_name: str,
        uri: str
    ) -> List[Dict[str, Any]]:
        """读取 MCP 资源。"""
        if server_name not in self._clients:
            raise RuntimeError(f"Server not found: {server_name}")

        client = self._clients[server_name]
        return await client.read_resource(uri)
