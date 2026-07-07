"""MCP 模块。

提供与 MCP 服务器通信的客户端实现。
"""

from .client import MCPClient
from .manager import MCPManager
from .types import (
    MCPServerConfig,
    MCPServerConnection,
    MCPServerConnectionStatus,
    MCPConfigScope,
    MCPResource,
    MCPTool,
    MCPTransportType,
)

__all__ = [
    "MCPServerConfig",
    "MCPTool",
    "MCPResource",
    "MCPServerConnection",
    "MCPTransportType",
    "MCPConfigScope",
    "MCPServerConnectionStatus",
    "MCPManager",
    "MCPClient",
    "initialize_mcp",
]


def initialize_mcp():
    """初始化 MCP 模块。"""
    return MCPManager()
