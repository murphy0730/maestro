"""Local stdio MCP configuration and runtime management API."""

import asyncio
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from maestro.config import MCPServerSettings
from maestro.foundation.settings_json_store import SettingsConflictError
from maestro.mcp.client import MCPClient
from maestro.mcp.types import MCPServerConfig, MCPTransportType
from maestro.api.security import require_privileged

router = APIRouter(prefix="/mcp")
_locks: dict[str, asyncio.Lock] = {}


class ServerInput(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    display_name: str | None = None
    description: str = ""
    transport_type: str = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env_keys: list[str] = Field(default_factory=list)
    enabled: bool = False
    expected_revision: int | None = None

    @field_validator("transport_type")
    @classmethod
    def stdio_only(cls, value: str) -> str:
        if value != "stdio":
            raise ValueError("v1 仅支持 stdio")
        return value


class RevisionInput(BaseModel):
    expected_revision: int


def _redact(server: MCPServerSettings, *, source: str = "settings_file", managed: bool = False) -> dict:
    secret = set(server.secret_env_keys)
    return {
        **server.model_dump(exclude={"env"}),
        "env": {key: {"configured": True, "secret": key in secret, "value": None if key in secret else value}
                for key, value in server.env.items()},
        "source": source, "managed": managed, "editable": not managed,
    }


def _status(platform, server: MCPServerSettings) -> dict:
    conn = platform.mcp.mcp_manager.get_connection(server.name)
    return {"status": str(conn.status.value) if conn else "disconnected",
            "tools_count": len(conn.tools) if conn else 0,
            "resources_count": len(conn.resources) if conn else 0,
            "error": conn.error if conn else None}


@router.get("/servers")
async def list_servers(request: Request):
    platform = request.app.state.platform
    stored, revision = platform.mcp_config_store.list()
    managed = {item.name: item for item in platform.settings.mcp_servers}
    editable = {item.name: item for item in stored if item.name not in managed}
    items = [(_redact(s) | _status(platform, s)) for s in editable.values()]
    items += [(_redact(s, source="environment", managed=True) | _status(platform, s)) for s in managed.values()]
    return {"servers": items, "revision": revision}


@router.post("/servers", status_code=201)
async def create_server(payload: ServerInput, request: Request, principal: str = Depends(require_privileged)):
    platform = request.app.state.platform
    servers, revision = platform.mcp_config_store.list()
    if any(s.name == payload.name for s in servers) or any(s.name == payload.name for s in platform.settings.mcp_servers):
        raise HTTPException(409, "连接器名称已存在")
    server = MCPServerSettings(**payload.model_dump(exclude={"expected_revision"}))
    try:
        new_revision = platform.mcp_config_store.save_all(servers + [server], payload.expected_revision if payload.expected_revision is not None else revision)
    except SettingsConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    platform.audit.record(principal, "mcp.create", {"name": server.name}, "allowed")
    return {**_redact(server), **_status(platform, server), "revision": new_revision}


@router.delete("/servers/{name}")
async def delete_server(name: str, payload: RevisionInput, request: Request, principal: str = Depends(require_privileged)):
    platform = request.app.state.platform
    if any(s.name == name for s in platform.settings.mcp_servers):
        raise HTTPException(403, "该连接器由环境管理")
    async with _locks.setdefault(name, asyncio.Lock()):
        servers, _ = platform.mcp_config_store.list()
        if not any(s.name == name for s in servers):
            raise HTTPException(404, "连接器不存在")
        await platform.mcp.mcp_manager.remove_server(name)
        await platform.refresh_mcp_tools()
        try:
            revision = platform.mcp_config_store.save_all([s for s in servers if s.name != name], payload.expected_revision)
        except SettingsConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
    platform.audit.record(principal, "mcp.delete", {"name": name}, "allowed")
    return {"deleted": True, "revision": revision}


async def _set_enabled(name: str, enabled: bool, expected_revision: int, request: Request):
    platform = request.app.state.platform
    if any(s.name == name for s in platform.settings.mcp_servers):
        raise HTTPException(403, "该连接器由环境管理")
    async with _locks.setdefault(name, asyncio.Lock()):
        servers, _ = platform.mcp_config_store.list()
        server = next((s for s in servers if s.name == name), None)
        if not server:
            raise HTTPException(404, "连接器不存在")
        server.enabled = enabled
        try:
            revision = platform.mcp_config_store.save_all(servers, expected_revision)
        except SettingsConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        if enabled:
            await platform.mcp.mcp_manager.add_server(MCPServerConfig(name=name, transport_type=MCPTransportType.STDIO, command=server.command, args=server.args, env=server.env))
            connection = await platform.mcp.mcp_manager.connect_server(name)
        else:
            await platform.mcp.mcp_manager.remove_server(name)
            connection = None
        await platform.refresh_mcp_tools()
        return {**_redact(server), **_status(platform, server), "revision": revision,
                "connected": bool(connection and connection.status.value == "connected")}


@router.post("/servers/{name}/connect")
async def connect(name: str, payload: RevisionInput, request: Request):
    principal = require_privileged(request)
    result = await _set_enabled(name, True, payload.expected_revision, request)
    request.app.state.platform.audit.record(principal, "mcp.connect", {"name": name}, "allowed")
    return result


@router.post("/servers/{name}/disconnect")
async def disconnect(name: str, payload: RevisionInput, request: Request):
    principal = require_privileged(request)
    result = await _set_enabled(name, False, payload.expected_revision, request)
    request.app.state.platform.audit.record(principal, "mcp.disconnect", {"name": name}, "allowed")
    return result


@router.post("/servers/test")
async def test_server(payload: ServerInput, request: Request, principal: str = Depends(require_privileged)):
    started = monotonic()
    client = MCPClient(MCPServerConfig(name=f"test-{payload.name}", transport_type=MCPTransportType.STDIO, command=payload.command, args=payload.args, env=payload.env))
    try:
        connection = await client.connect()
        return {"ok": connection.status.value == "connected", "duration_ms": int((monotonic() - started) * 1000),
                "status": connection.status.value,
                "tools": [{"name": t.name, "description": t.description} for t in connection.tools],
                "resources": [{"uri": r.uri, "name": r.name, "mime_type": r.mime_type} for r in connection.resources],
                "error": connection.error}
    except Exception as exc:
        return {"ok": False, "duration_ms": int((monotonic() - started) * 1000), "status": "error", "tools": [], "resources": [], "error": str(exc)}
    finally:
        await client.disconnect()
        request.app.state.platform.audit.record(principal, "mcp.test", {"name": payload.name}, "allowed")
