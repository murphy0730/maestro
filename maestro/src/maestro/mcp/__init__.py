"""MCP client: stdio transport, protocol handshake, and capability publication.

The Runtime stays transport-agnostic — `runtime/mcp.py` owns the governed
registration boundary, and this package is what actually talks to a server.
"""

from maestro.mcp.client import DEFAULT_CALL_TIMEOUT, PROTOCOL_VERSION, MCPClient
from maestro.mcp.manager import MCPManager
from maestro.mcp.transport import MCPTransportError, StdioMCPTransport
from maestro.mcp.types import (
    MCPConnection,
    MCPConnectionStatus,
    MCPServerConfig,
    MCPTool,
)

__all__ = [
    "DEFAULT_CALL_TIMEOUT",
    "PROTOCOL_VERSION",
    "MCPClient",
    "MCPConnection",
    "MCPConnectionStatus",
    "MCPManager",
    "MCPServerConfig",
    "MCPTool",
    "MCPTransportError",
    "StdioMCPTransport",
]
