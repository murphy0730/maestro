"""MCP 客户端（协议层）。

提供与 MCP 服务器通信的客户端实现。
"""

import time
from typing import Any, Dict, List, Optional

from .discovery import discover_resources_from_response, discover_tools_from_response
from .execution import call_mcp_tool, read_mcp_resource
from .transport import MCPTransport, StdioMCPTransport
from .types import (
    MCPServerConfig,
    MCPServerConnection,
    MCPServerConnectionStatus,
    MCPResource,
    MCPTool,
)


class MCPClient:
    """MCP 客户端，协议层实现。"""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._transport: Optional[MCPTransport] = None
        self._request_id = 0
        self._session_id: Optional[str] = None
        self._tools: List[MCPTool] = []
        self._resources: List[MCPResource] = []

    def _next_id(self) -> int:
        """获取下一个请求 ID（统一来源）。"""
        self._request_id += 1
        return self._request_id

    async def connect(self) -> MCPServerConnection:
        """连接到 MCP 服务器。"""
        if self.config.transport_type == "stdio":
            self._transport = StdioMCPTransport(self.config)
        else:
            raise ValueError(f"Unsupported transport: {self.config.transport_type}")

        try:
            await self._transport.connect()

            await self._initialize()
            await self._send_initialized_notification()
            await self._list_tools()
            await self._list_resources()

            return MCPServerConnection(
                name=self.config.name,
                config=self.config,
                status=MCPServerConnectionStatus.CONNECTED,
                tools=self._tools,
                resources=self._resources
            )
        except Exception as e:
            return MCPServerConnection(
                name=self.config.name,
                config=self.config,
                status=MCPServerConnectionStatus.ERROR,
                error=str(e)
            )

    async def disconnect(self) -> None:
        """断开与 MCP 服务器的连接。"""
        if self._transport:
            await self._transport.disconnect()
            self._transport = None

    async def _initialize(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")

        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "clientInfo": {
                    "name": "manufacturing-agent",
                    "version": "0.1.0"
                }
            }
        }

        await self._transport.send_message(request)
        response = await self._transport.receive_response(request_id, timeout=30.0)

        if response is None:
            raise TimeoutError("MCP initialize timed out")
        if 'error' in response:
            raise RuntimeError(f"MCP initialize error: {response['error'].get('message')}")

        self._session_id = response.get('result', {}).get('sessionId')

    async def _send_initialized_notification(self) -> None:
        """发送 notifications/initialized 通知（MCP 规范要求）。"""
        if not self._transport:
            raise RuntimeError("Not connected")

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        await self._transport.send_message(notification)

    async def _list_tools(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")

        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list"
        }

        await self._transport.send_message(request)
        response = await self._transport.receive_response(request_id, timeout=30.0)

        if response and 'error' not in response:
            self._tools = discover_tools_from_response(self.config.name, response)
        else:
            self._tools = []

    async def _list_resources(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")

        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "resources/list"
        }

        await self._transport.send_message(request)
        response = await self._transport.receive_response(request_id, timeout=30.0)

        if response and 'error' not in response:
            self._resources = discover_resources_from_response(response)
        else:
            self._resources = []

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """调用 MCP 工具。"""
        if not self._transport:
            raise RuntimeError("Not connected")

        return await call_mcp_tool(self._transport, tool_name, arguments, self._next_id)

    async def read_resource(self, uri: str) -> List[Dict[str, Any]]:
        """读取 MCP 资源。"""
        if not self._transport:
            raise RuntimeError("Not connected")

        return await read_mcp_resource(self._transport, uri, self._next_id)

    def get_tools(self) -> List[MCPTool]:
        """获取所有可用工具。"""
        return self._tools

    def get_resources(self) -> List[MCPResource]:
        """获取所有可用资源。"""
        return self._resources
