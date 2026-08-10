"""Connecting configured MCP servers and publishing their tools as capabilities.

Only local configuration can grant a remote tool read-only trust.  Remote
annotations may veto that downgrade when they explicitly describe a write or
destructive action, but can never lower risk.  Everything else is registered as
a HIGH-risk write, which the Policy Gate turns into human approval before calls.
"""

from __future__ import annotations

from dataclasses import replace
import logging

from maestro.mcp.client import MCPClient, MCPToolError
from maestro.mcp.types import MCPConnection, MCPConnectionStatus, MCPServerConfig
from maestro.runtime.capabilities import CapabilityResult, RiskLevel
from maestro.runtime.mcp import MCPCapabilityConflict, MCPConnector

logger = logging.getLogger(__name__)


class MCPManager:
    """Owns the lifecycle of every configured MCP server."""

    def __init__(self, connector: MCPConnector) -> None:
        self._connector = connector
        self._clients: dict[str, MCPClient] = {}
        self._connections: dict[str, MCPConnection] = {}
        self._registered: dict[str, set[str]] = {}

    @property
    def connections(self) -> dict[str, MCPConnection]:
        return dict(self._connections)

    async def connect(self, config: MCPServerConfig) -> MCPConnection:
        """Start one server, then publish its tools. Failure is returned, not raised."""
        await self.disconnect(config.name)
        if not config.enabled:
            connection = MCPConnection(
                name=config.name, status=MCPConnectionStatus.DISCONNECTED
            )
            self._connections[config.name] = connection
            return connection

        client = MCPClient(config)
        connection = await client.connect()
        if connection.status is not MCPConnectionStatus.CONNECTED:
            await client.disconnect()
            self._connections[config.name] = connection
            logger.warning("[mcp] %s 连接失败: %s", config.name, connection.error)
            return connection

        self._clients[config.name] = client
        registered: set[str] = set()
        rejected: list[str] = []
        for tool in connection.tools:
            configured_read_only = tool.name in config.read_only_tools
            remote_requires_governance = (
                tool.annotations.get("readOnlyHint") is False
                or tool.annotations.get("destructiveHint") is True
            )
            is_read_only = configured_read_only and not remote_requires_governance
            if configured_read_only and remote_requires_governance:
                logger.warning(
                    "[mcp] %s/%s 被本地配置为只读，但远端明确标注为写/破坏性操作；保留高风险治理",
                    config.name,
                    tool.name,
                )
            try:
                self._connector.register(
                    config.name,
                    tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    writes=not is_read_only,
                    risk=RiskLevel.LOW if is_read_only else RiskLevel.HIGH,
                    idempotent=is_read_only,
                    executor=_executor_for(client),
                )
            except MCPCapabilityConflict as error:
                rejected.append(f"{tool.name}（{error}）")
                continue
            registered.add(tool.name)
        self._registered[config.name] = registered
        if rejected:
            logger.warning("[mcp] %s 的部分工具未注册: %s", config.name, "; ".join(rejected))
            connection = replace(
                connection,
                tools=tuple(item for item in connection.tools if item.name in registered),
                error=f"部分工具名与既有能力冲突，未注册: {'; '.join(rejected)}",
            )
        self._connections[config.name] = connection
        return connection

    async def disconnect(self, name: str) -> None:
        for tool_name in self._registered.pop(name, set()):
            self._connector.unregister(name, tool_name)
        client = self._clients.pop(name, None)
        if client is not None:
            await client.disconnect()
        self._connections.pop(name, None)

    async def connect_all(self, configs: list[MCPServerConfig]) -> dict[str, MCPConnection]:
        for config in configs:
            await self.connect(config)
        return self.connections

    async def shutdown(self) -> None:
        for name in list(self._clients):
            await self.disconnect(name)


def _executor_for(client: MCPClient):
    async def execute(tool_name: str, arguments: dict) -> object:
        try:
            return await client.call_tool(tool_name, dict(arguments))
        except MCPToolError as error:
            return CapabilityResult(status="failed", error_message=str(error))

    return execute
