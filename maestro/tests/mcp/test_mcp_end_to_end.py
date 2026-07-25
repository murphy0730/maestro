"""MCP from configuration to a governed capability call.

The connector used to be a bare registration hook with no transport at all, and
its result wrapper reported every outcome as success.  These tests pin the whole
path: handshake, discovery, registration, the Policy Gate, and the failure modes
that must arrive as data rather than as an exception.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from maestro.mcp import MCPClient, MCPManager, MCPServerConfig, MCPTransportError
from maestro.mcp.types import MCPConnectionStatus
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.mcp import MCPCapabilityConflict, MCPConnector

pytestmark = pytest.mark.asyncio

SERVER = Path(__file__).parent / "servers" / "echo_server.py"


def config(name: str = "echo", **env: str) -> MCPServerConfig:
    return MCPServerConfig(name=name, command=sys.executable, args=(str(SERVER),), env=env)


async def test_handshake_discovers_tools() -> None:
    client = MCPClient(config())
    connection = await client.connect()
    try:
        assert connection.status is MCPConnectionStatus.CONNECTED
        assert {tool.name for tool in connection.tools} == {"echo", "leak_env"}
        echo = next(tool for tool in connection.tools if tool.name == "echo")
        assert echo.input_schema["required"] == ["text"]
    finally:
        await client.disconnect()


async def test_tool_call_round_trips() -> None:
    client = MCPClient(config())
    await client.connect()
    try:
        result = await client.call_tool("echo", {"text": "你好"})
        assert json.loads(result["content"][0]["text"]) == "你好"
    finally:
        await client.disconnect()


async def test_manager_publishes_tools_as_governed_capabilities() -> None:
    registry = CapabilityRegistry()
    manager = MCPManager(MCPConnector(registry))
    try:
        connection = await manager.connect(config())
        assert connection.status is MCPConnectionStatus.CONNECTED

        spec = registry.require("mcp__echo__echo")
        assert spec.kind is CapabilityKind.MCP
        # The Runtime cannot know what a remote tool touches, so it is governed
        # as a high-risk write and the Policy Gate demands human approval.
        assert spec.writes is True
        assert spec.risk is RiskLevel.HIGH

        result = await spec.executor(
            CapabilityCall(name="mcp__echo__echo", arguments={"text": "hi"}), None
        )
        assert result.status == "succeeded"
        assert json.loads(result.content["content"][0]["text"]) == "hi"
    finally:
        await manager.shutdown()


async def test_disconnect_removes_the_capabilities() -> None:
    registry = CapabilityRegistry()
    manager = MCPManager(MCPConnector(registry))
    await manager.connect(config())
    assert registry.require("mcp__echo__echo") is not None

    await manager.disconnect("echo")

    with pytest.raises(KeyError):
        registry.require("mcp__echo__echo")


async def test_remote_error_becomes_a_failed_result_not_a_success() -> None:
    """The old wrapper returned status='succeeded' unconditionally."""
    registry = CapabilityRegistry()
    manager = MCPManager(MCPConnector(registry))
    try:
        await manager.connect(config(ECHO_FAIL_TOOL="1"))
        spec = registry.require("mcp__echo__echo")

        result = await spec.executor(
            CapabilityCall(name="mcp__echo__echo", arguments={"text": "x"}), None
        )

        assert result.status == "failed"
        assert "工具执行失败" in (result.error_message or "")
    finally:
        await manager.shutdown()


async def test_a_hanging_tool_call_times_out_instead_of_blocking() -> None:
    client = MCPClient(config(ECHO_HANG_TOOL="1"))
    await client.connect()
    try:
        with pytest.raises(MCPTransportError) as error:
            await client.call_tool("echo", {"text": "x"}, timeout=0.5)
        assert "超时" in str(error.value)
    finally:
        await client.disconnect()


async def test_server_does_not_inherit_host_secrets(monkeypatch) -> None:
    """The previous transport passed the whole environment, including LLM_API_KEY."""
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    client = MCPClient(config(GRANTED="yes"))
    await client.connect()
    try:
        result = await client.call_tool("leak_env", {})
        names = json.loads(result["content"][0]["text"])
        assert "LLM_API_KEY" not in names
        # Explicitly configured values still reach the server.
        assert "GRANTED" in names
    finally:
        await client.disconnect()


async def test_a_noisy_server_does_not_deadlock() -> None:
    """stderr was never drained, so a chatty server filled the pipe and hung."""
    client = MCPClient(config(ECHO_NOISY="1"))
    connection = await client.connect()
    try:
        assert connection.status is MCPConnectionStatus.CONNECTED
        assert await client.call_tool("echo", {"text": "ok"})
    finally:
        await client.disconnect()


async def test_a_non_json_line_does_not_kill_the_channel() -> None:
    client = MCPClient(config(ECHO_BAD_LINE="1"))
    connection = await client.connect()
    try:
        assert connection.status is MCPConnectionStatus.CONNECTED
    finally:
        await client.disconnect()


async def test_unstartable_server_reports_error_without_raising() -> None:
    client = MCPClient(MCPServerConfig(name="missing", command="/nonexistent/binary"))
    connection = await client.connect()

    assert connection.status is MCPConnectionStatus.ERROR
    assert connection.error


async def test_mcp_may_not_shadow_a_host_tool() -> None:
    """Skills are barred from replacing a TOOL; MCP had no such protection."""
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="mcp__echo__echo", kind=CapabilityKind.TOOL))
    connector = MCPConnector(registry)

    async def executor(_name: str, _arguments: dict) -> object:
        return {}

    with pytest.raises(MCPCapabilityConflict):
        connector.register("echo", "echo", executor=executor)

    assert registry.require("mcp__echo__echo").kind is CapabilityKind.TOOL


async def test_reconnect_refreshes_its_own_entry() -> None:
    registry = CapabilityRegistry()
    manager = MCPManager(MCPConnector(registry))
    try:
        await manager.connect(config())
        await manager.connect(config())
        assert registry.require("mcp__echo__echo").kind is CapabilityKind.MCP
    finally:
        await manager.shutdown()


async def test_disabled_server_is_not_connected() -> None:
    registry = CapabilityRegistry()
    manager = MCPManager(MCPConnector(registry))
    disabled = MCPServerConfig(
        name="echo", command=sys.executable, args=(str(SERVER),), enabled=False
    )

    connection = await manager.connect(disabled)

    assert connection.status is MCPConnectionStatus.DISCONNECTED
    with pytest.raises(KeyError):
        registry.require("mcp__echo__echo")
