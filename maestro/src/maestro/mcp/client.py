"""MCP protocol client: handshake, tool discovery, tool invocation.

Everything the model can reach goes through `call_tool`; the descriptive
metadata `list_tools` returns never decides authorization — that stays with the
local registration in `runtime/mcp.py` and the Policy Gate.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from time import monotonic, time
from urllib.parse import urlparse
import webbrowser

from maestro.mcp.transport import MCPTransportError, StdioMCPTransport
from maestro.mcp.types import MCPConnection, MCPConnectionStatus, MCPServerConfig, MCPTool

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "maestro", "version": "1"}

_HANDSHAKE_TIMEOUT = 30.0
_DISCOVERY_TIMEOUT = 30.0
DEFAULT_CALL_TIMEOUT = 60.0
_MAX_TOOL_ERROR_CHARS = 2_000
_MAX_BROWSER_AUTH_WAIT_SECONDS = 5 * 60.0
_MIN_AUTH_RETRY_SECONDS = 0.2
_MAX_AUTH_RETRY_SECONDS = 2.0


class MCPToolError(MCPTransportError):
    """The MCP server completed the request but reported tool failure."""


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
            initialization = await self._initialize()
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
        server_info = initialization.get("serverInfo")
        instructions = initialization.get("instructions")
        return MCPConnection(
            name=self._config.name,
            status=MCPConnectionStatus.CONNECTED,
            tools=tools,
            protocol_version=initialization["protocolVersion"],
            server_info=dict(server_info) if isinstance(server_info, dict) else {},
            instructions=instructions if isinstance(instructions, str) else "",
        )

    async def disconnect(self) -> None:
        self._connected = False
        await self._transport.disconnect()

    async def _initialize(self) -> dict:
        response = await self._transport.request(
            self._next_id(),
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": _CLIENT_INFO,
                },
            },
            timeout=_HANDSHAKE_TIMEOUT,
        )
        result = _result_object(response, "initialize")
        negotiated = result.get("protocolVersion")
        if negotiated != PROTOCOL_VERSION:
            raise MCPTransportError(
                f"MCP 服务器协商了不支持的协议版本: {negotiated!r}"
            )
        return result

    async def ping(self, timeout: float = _HANDSHAKE_TIMEOUT) -> None:
        """Check that a connected server can still answer JSON-RPC requests."""
        response = await self._transport.request(
            self._next_id(),
            {"jsonrpc": "2.0", "id": self._request_id, "method": "ping"},
            timeout=timeout,
        )
        _result_object(response, "ping")

    async def list_tools(self) -> tuple[MCPTool, ...]:
        response = await self._transport.request(
            self._next_id(),
            {"jsonrpc": "2.0", "id": self._request_id, "method": "tools/list"},
            timeout=_DISCOVERY_TIMEOUT,
        )
        result = _result_object(response, "tools/list")
        definitions = result.get("tools", [])
        if not isinstance(definitions, list):
            raise MCPTransportError("MCP tools/list 返回了无效工具列表")
        tools = []
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            name = definition.get("name")
            if not isinstance(name, str) or not name:
                continue
            schema = definition.get("inputSchema")
            description = definition.get("description")
            annotations = definition.get("annotations")
            tools.append(
                MCPTool(
                    name=name,
                    description=description if isinstance(description, str) else "",
                    input_schema=schema if isinstance(schema, dict) else {"type": "object"},
                    server_name=self._config.name,
                    annotations=dict(annotations) if isinstance(annotations, dict) else {},
                )
            )
        return tuple(tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        timeout: float = DEFAULT_CALL_TIMEOUT,
        *,
        principal_id: str | None = None,
    ) -> dict:
        opened_challenge: str | None = None
        auth_deadline: float | None = None
        while True:
            params: dict[str, object] = {"name": tool_name, "arguments": arguments}
            if principal_id:
                params["_meta"] = {"maestro/principalId": principal_id}
            response = await self._transport.request(
                self._next_id(),
                {
                    "jsonrpc": "2.0",
                    "id": self._request_id,
                    "method": "tools/call",
                    "params": params,
                },
                timeout=timeout,
            )
            result = _result_object(response, "tools/call")
            challenge = _browser_auth_challenge(result)
            if challenge is None:
                if result.get("isError") is True:
                    raise MCPToolError(_extract_tool_error(result))
                return result

            challenge_id = challenge["challenge_id"]
            if challenge_id != opened_challenge:
                try:
                    await asyncio.to_thread(
                        webbrowser.open, challenge["login_url"], new=2
                    )
                except Exception:  # noqa: BLE001 - the retry still exposes a bounded error
                    logger.exception("[mcp] 无法打开登录浏览器")
                opened_challenge = challenge_id
                auth_deadline = monotonic() + min(
                    _MAX_BROWSER_AUTH_WAIT_SECONDS,
                    max(1.0, challenge["expires_at"] - time()),
                )
            if auth_deadline is None or monotonic() >= auth_deadline:
                raise MCPToolError(
                    f"{_extract_tool_error(result)}：{challenge['login_url']}"
                )
            await asyncio.sleep(challenge["retry_seconds"])


def _raise_for_error(response: dict) -> None:
    error = response.get("error")
    if error is None:
        return
    message = error.get("message", "unknown error") if isinstance(error, dict) else str(error)
    raise MCPTransportError(f"MCP 服务器返回错误: {message}")


def _result_object(response: dict, method: str) -> dict:
    _raise_for_error(response)
    result = response.get("result")
    if not isinstance(result, dict):
        raise MCPTransportError(f"MCP {method} 返回了无效结果")
    return result


def _extract_tool_error(result: dict) -> str:
    texts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    detail = "\n".join(texts).strip() or "MCP 工具返回 isError=true"
    return detail[:_MAX_TOOL_ERROR_CHARS]


def _browser_auth_challenge(result: dict) -> dict[str, object] | None:
    """Accept only an explicit MCP auth challenge pointing at this machine."""
    if result.get("isError") is not True:
        return None
    payload = result.get("structuredContent")
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict) or error.get("code") != "AUTH_REQUIRED":
        return None
    login_url = error.get("login_url")
    challenge_id = error.get("challenge_id")
    if not isinstance(login_url, str) or not isinstance(challenge_id, str):
        return None
    parsed = urlparse(login_url)
    if parsed.scheme not in {"http", "https"} or not _is_loopback_host(parsed.hostname):
        return None
    try:
        expires_at = float(error.get("expires_at"))
    except (TypeError, ValueError):
        expires_at = time() + _MAX_BROWSER_AUTH_WAIT_SECONDS
    try:
        retry_seconds = float(error.get("retry_after_ms", 750)) / 1000.0
    except (TypeError, ValueError):
        retry_seconds = 0.75
    return {
        "challenge_id": challenge_id,
        "login_url": login_url,
        "expires_at": expires_at,
        "retry_seconds": max(
            _MIN_AUTH_RETRY_SECONDS,
            min(retry_seconds, _MAX_AUTH_RETRY_SECONDS),
        ),
    }


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
