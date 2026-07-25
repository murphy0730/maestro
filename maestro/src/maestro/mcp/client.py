"""MCP protocol client: handshake, tool discovery, tool invocation.

Everything the model can reach goes through `call_tool`; the descriptive
metadata `list_tools` returns never decides authorization — that stays with the
local registration in `runtime/mcp.py` and the Policy Gate.
"""

from __future__ import annotations

import logging

from maestro.mcp.transport import MCPTransportError, StdioMCPTransport
from maestro.mcp.types import MCPConnection, MCPConnectionStatus, MCPServerConfig, MCPTool

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "maestro", "version": "1"}

_HANDSHAKE_TIMEOUT = 30.0
_DISCOVERY_TIMEOUT = 30.0
DEFAULT_CALL_TIMEOUT = 60.0


class MCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._transport = StdioMCPTransport(config)
        self._request_id = 0
        self._connected = False

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def connect(self) -> MCPConnection:
        """Start the server and complete the handshake, reporting failure as data."""
        try:
            await self._transport.connect()
            await self._initialize()
            await self._transport.notify(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
            tools = await self.list_tools()
        except (MCPTransportError, ValueError) as error:
            detail = self._transport.stderr.strip()
            await self._transport.disconnect()
            self._connected = False
            return MCPConnection(
                name=self._config.name,
                status=MCPConnectionStatus.ERROR,
                error=f"{error}" + (f"\n{detail[-2000:]}" if detail else ""),
            )
        self._connected = True
        return MCPConnection(
            name=self._config.name, status=MCPConnectionStatus.CONNECTED, tools=tools
        )

    async def disconnect(self) -> None:
        self._connected = False
        await self._transport.disconnect()

    async def _initialize(self) -> None:
        response = await self._transport.request(
            self._next_id(),
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "clientInfo": _CLIENT_INFO,
                },
            },
            timeout=_HANDSHAKE_TIMEOUT,
        )
        _raise_for_error(response)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        response = await self._transport.request(
            self._next_id(),
            {"jsonrpc": "2.0", "id": self._request_id, "method": "tools/list"},
            timeout=_DISCOVERY_TIMEOUT,
        )
        _raise_for_error(response)
        definitions = response.get("result", {}).get("tools", [])
        tools = []
        for definition in definitions:
            name = definition.get("name")
            if not isinstance(name, str) or not name:
                continue
            schema = definition.get("inputSchema")
            tools.append(
                MCPTool(
                    name=name,
                    description=definition.get("description", "") or "",
                    input_schema=schema if isinstance(schema, dict) else {"type": "object"},
                    server_name=self._config.name,
                )
            )
        return tuple(tools)

    async def call_tool(
        self, tool_name: str, arguments: dict, timeout: float = DEFAULT_CALL_TIMEOUT
    ) -> dict:
        response = await self._transport.request(
            self._next_id(),
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            timeout=timeout,
        )
        _raise_for_error(response)
        return response.get("result", {})


def _raise_for_error(response: dict) -> None:
    error = response.get("error")
    if error is None:
        return
    message = error.get("message", "unknown error") if isinstance(error, dict) else str(error)
    raise MCPTransportError(f"MCP 服务器返回错误: {message}")
