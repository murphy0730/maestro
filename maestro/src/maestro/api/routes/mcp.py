"""MCP server administration.

Configuring an MCP server installs new capabilities into the Runtime, which is a
host-administration act, not something the model may do.  Every mutating route
therefore sits behind `require_privileged` and returns 403 — never 401 — exactly
like the Skill package APIs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from maestro.api.security import require_privileged
from maestro.mcp.types import (
    MCPConnectionStatus,
    MCPServerConfig,
    normalize_read_only_tools,
)

router = APIRouter()


class MCPServerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    read_only_tools: list[str] = Field(default_factory=list)

    @field_validator("read_only_tools")
    @classmethod
    def validate_read_only_tools(cls, value: list[str]) -> list[str]:
        return list(normalize_read_only_tools(value))

    def to_config(self) -> MCPServerConfig:
        return MCPServerConfig(
            name=self.name,
            command=self.command,
            args=tuple(self.args),
            env=dict(self.env),
            enabled=self.enabled,
            read_only_tools=tuple(self.read_only_tools),
        )


def _platform(request: Request):
    return request.app.state.platform


def _view(config: MCPServerConfig, platform) -> dict:
    connection = platform.mcp_manager.connections.get(config.name)
    status = connection.status if connection else MCPConnectionStatus.DISCONNECTED
    return {
        "name": config.name,
        "command": config.command,
        "args": list(config.args),
        # Values are secrets often enough that echoing them back is not worth it.
        "env_keys": sorted(config.env),
        "enabled": config.enabled,
        "read_only_tools": list(config.read_only_tools),
        "status": status.value,
        "error": connection.error if connection else "",
        "tools": [
            _tool_view(config, tool, platform)
            for tool in (connection.tools if connection else ())
        ],
    }


def _tool_view(config: MCPServerConfig, tool, platform) -> dict:
    capability = f"mcp__{config.name}__{tool.name}"
    spec = platform.capabilities.require(capability)
    return {
        "name": tool.name,
        "capability": capability,
        "description": tool.description,
        # Show effective policy, which may stay strict when the remote explicitly
        # marks a locally allowlisted tool as a write or destructive action.
        "read_only": not spec.writes,
        "writes": spec.writes,
        "risk": spec.risk.value,
    }


@router.get("/mcp/servers")
async def list_servers(request: Request):
    """Read-only: what is configured and whether it actually came up."""
    platform = _platform(request)
    return {"servers": [_view(config, platform) for config in platform.mcp_config.load()]}


@router.put("/mcp/servers/{name}")
async def upsert_server(
    name: str, payload: MCPServerPayload, request: Request, _: str = Depends(require_privileged)
):
    if name != payload.name:
        raise HTTPException(status_code=400, detail="路径中的名称与请求体不一致")
    platform = _platform(request)
    config = payload.to_config()
    platform.mcp_config.upsert(config)
    await platform.mcp_manager.connect(config)
    return _view(config, platform)


@router.delete("/mcp/servers/{name}")
async def delete_server(name: str, request: Request, _: str = Depends(require_privileged)):
    platform = _platform(request)
    if not platform.mcp_config.delete(name):
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    await platform.mcp_manager.disconnect(name)
    return {"name": name, "deleted": True}


@router.post("/mcp/servers/{name}/reconnect")
async def reconnect_server(name: str, request: Request, _: str = Depends(require_privileged)):
    platform = _platform(request)
    config = next((item for item in platform.mcp_config.load() if item.name == name), None)
    if config is None:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    await platform.mcp_manager.connect(config)
    return _view(config, platform)
