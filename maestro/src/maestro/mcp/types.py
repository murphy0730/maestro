"""MCP wire types, narrowed to what this host actually implements.

Only stdio is modelled: an enum value for a transport with no client behind it
would be a promise the code cannot keep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re


MCP_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def normalize_read_only_tools(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Validate local trust entries and remove duplicates without reordering."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or MCP_TOOL_NAME_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "MCP 只读工具名必须为 1-64 位字母、数字、下划线或连字符"
            )
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


class MCPConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True)
class MCPServerConfig:
    """How to start one stdio MCP server."""

    name: str
    command: str
    args: tuple[str, ...] = ()
    # Passed through to the child on top of the inherited allowlist.  Secrets a
    # server genuinely needs are named here rather than leaked wholesale.
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    read_only_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "read_only_tools", normalize_read_only_tools(self.read_only_tools)
        )

    @classmethod
    def from_dict(cls, name: str, raw: dict) -> "MCPServerConfig":
        command = raw.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError(f"MCP 服务器 {name} 缺少 command")
        args = raw.get("args") or []
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise ValueError(f"MCP 服务器 {name} 的 args 必须是字符串数组")
        env = raw.get("env") or {}
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()
        ):
            raise ValueError(f"MCP 服务器 {name} 的 env 必须是字符串字典")
        read_only_tools = raw.get("read_only_tools", [])
        if not isinstance(read_only_tools, list):
            raise ValueError(f"MCP 服务器 {name} 的 read_only_tools 必须是字符串数组")
        return cls(
            name=name,
            command=command,
            args=tuple(args),
            env=dict(env),
            enabled=bool(raw.get("enabled", True)),
            read_only_tools=normalize_read_only_tools(read_only_tools),
        )

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "enabled": self.enabled,
            "read_only_tools": list(self.read_only_tools),
        }


@dataclass(frozen=True)
class MCPTool:
    """One tool as the remote described it.

    Purely descriptive: risk, write and idempotency metadata are decided locally
    when this is registered as a capability, never by the server.
    """

    name: str
    description: str
    input_schema: dict
    server_name: str


@dataclass
class MCPConnection:
    name: str
    status: MCPConnectionStatus
    tools: tuple[MCPTool, ...] = ()
    error: str = ""
