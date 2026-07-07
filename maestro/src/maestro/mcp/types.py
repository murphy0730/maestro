"""MCP 类型定义。

定义 MCP 协议相关的数据类型。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class MCPTransportType(str, Enum):
    """MCP 传输类型。"""
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"
    HTTP = "http"


class MCPConfigScope(str, Enum):
    """配置作用域。"""
    DYNAMIC = "dynamic"
    PROJECT = "project"
    USER = "user"
    LOCAL = "local"
    ENTERPRISE = "enterprise"
    MANAGED = "managed"
    CLAUDEAI = "claudeai"


@dataclass
class MCPServerConfig:
    """MCP 服务器配置。"""
    name: str
    transport_type: MCPTransportType
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    scope: MCPConfigScope = MCPConfigScope.PROJECT


@dataclass
class MCPTool:
    """MCP 工具定义。"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResource:
    """MCP 资源定义。"""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


@dataclass
class MCPResourceContents:
    """MCP 资源内容。"""
    uri: str
    text: Optional[str] = None
    blob: Optional[bytes] = None
    mime_type: str = "text/plain"


class MCPServerConnectionStatus(str, Enum):
    """MCP 服务器连接状态。"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    NEEDS_AUTH = "needs_auth"


@dataclass
class MCPServerConnection:
    """MCP 服务器连接信息。"""
    name: str
    config: MCPServerConfig
    status: MCPServerConnectionStatus
    tools: List[MCPTool] = field(default_factory=list)
    resources: List[MCPResource] = field(default_factory=list)
    error: Optional[str] = None
