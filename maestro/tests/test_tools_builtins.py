"""新迁移内置工具的测试: glob / todo_write / tool_search / sleep / web_fetch / MCP 资源工具。

不发真实网络请求；文件类工具只读项目内已有文件。
"""

import pytest

from maestro.mcp.manager import MCPManager
from maestro.mcp.types import (
    MCPResource,
    MCPServerConfig,
    MCPServerConnection,
    MCPServerConnectionStatus,
    MCPTransportType,
    MCPTool,
)
from maestro.tools import (
    ToolManager,
    ToolResultStatus,
    ToolRegistry as FrameworkRegistry,
    initialize_tools,
    registry,
)
from maestro.tools.base import ToolDef, ToolResult, build_tool
from maestro.tools.builtins import register_all_builtins
from maestro.tools.mcp_resources import create_mcp_resource_tools

from pydantic import BaseModel


@pytest.fixture(autouse=True)
def clean_registry():
    """备份/还原单例注册表，避免测试间污染。"""
    snapshot = dict(registry._tools)
    registry._tools.clear()
    register_all_builtins()
    yield
    registry._tools.clear()
    registry._tools.update(snapshot)


@pytest.fixture
def manager():
    return ToolManager()


# ---------- glob ----------

async def test_glob_finds_files(manager):
    result = await manager.execute_tool("glob", {"pattern": "*.toml"}, context={})
    assert result.status == ToolResultStatus.SUCCESS
    assert "pyproject.toml" in result.content["filenames"]
    assert result.content["truncated"] is False


async def test_glob_rejects_escape(manager):
    result = await manager.execute_tool(
        "glob", {"pattern": "*.py", "path": "../"}, context={})
    assert result.status == ToolResultStatus.ERROR


async def test_glob_rejects_absolute_pattern(manager):
    result = await manager.execute_tool(
        "glob", {"pattern": "/etc/*"}, context={})
    assert result.status == ToolResultStatus.ERROR


# ---------- todo_write ----------

async def test_todo_write_roundtrip(manager):
    ctx = {"session_id": "t-session"}
    r1 = await manager.execute_tool("todo_write", {
        "todos": [
            {"content": "步骤一", "status": "completed"},
            {"content": "步骤二", "status": "in_progress"},
        ]
    }, context=ctx)
    assert r1.status == ToolResultStatus.SUCCESS
    assert r1.content["old_todos"] == []
    assert len(r1.content["new_todos"]) == 2

    r2 = await manager.execute_tool("todo_write", {
        "todos": [
            {"content": "步骤一", "status": "completed"},
            {"content": "步骤二", "status": "completed"},
        ]
    }, context=ctx)
    assert len(r2.content["old_todos"]) == 2

    # 全部完成后清空存储
    r3 = await manager.execute_tool(
        "todo_write", {"todos": [{"content": "新任务", "status": "pending"}]},
        context=ctx)
    assert r3.content["old_todos"] == []


async def test_todo_write_rejects_bad_status(manager):
    result = await manager.execute_tool(
        "todo_write", {"todos": [{"content": "x", "status": "done"}]}, context={})
    assert result.status == ToolResultStatus.ERROR


# ---------- tool_search ----------

class _NoArgs(BaseModel):
    pass


def _make_deferred_tool(name: str, description: str, hint: str):
    async def _exec(args, context, on_progress=None):
        return ToolResult(status=ToolResultStatus.SUCCESS, content="ok")
    return build_tool(ToolDef(
        name=name, description=description, input_schema=_NoArgs,
        execute=_exec, should_defer=True, search_hint=hint,
    ))


async def test_tool_search_select(manager):
    registry.register(_make_deferred_tool("demo_deferred", "示例延迟工具", "demo"))
    result = await manager.execute_tool(
        "tool_search", {"query": "select:demo_deferred"}, context={})
    assert result.status == ToolResultStatus.SUCCESS
    assert result.content["matches"][0]["name"] == "demo_deferred"
    assert "input_schema" in result.content["matches"][0]


async def test_tool_search_select_already_loaded(manager):
    result = await manager.execute_tool(
        "tool_search", {"query": "select:grep"}, context={})
    assert result.content["matches"] == []
    assert "grep" in result.content["already_loaded"]


async def test_tool_search_keywords(manager):
    registry.register(_make_deferred_tool("kit_check", "check kitting readiness", "kitting"))
    registry.register(_make_deferred_tool("other_tool", "unrelated", "misc"))
    result = await manager.execute_tool(
        "tool_search", {"query": "+kitting readiness"}, context={})
    names = [m["name"] for m in result.content["matches"]]
    assert names == ["kit_check"]


async def test_tool_search_is_initial_loaded():
    names = [t["name"] for t in registry.to_anthropic_tools()]
    assert "tool_search" in names
    assert "web_fetch" not in names  # deferred


# ---------- sleep ----------

async def test_sleep(manager):
    result = await manager.execute_tool("sleep", {"seconds": 0.01}, context={})
    assert result.status == ToolResultStatus.SUCCESS
    assert result.content["slept_seconds"] == 0.01


async def test_sleep_rejects_over_limit(manager):
    result = await manager.execute_tool("sleep", {"seconds": 301}, context={})
    assert result.status == ToolResultStatus.ERROR


# ---------- web_fetch ----------

async def test_web_fetch_invalid_url(manager):
    # requires_confirm 之前先过 validate_input，非法 URL 直接报错
    result = await manager.execute_tool(
        "web_fetch", {"url": "not-a-url"}, context={})
    assert result.status == ToolResultStatus.ERROR
    assert "Invalid URL" in result.error_message


async def test_web_fetch_requires_confirmation(manager):
    result = await manager.execute_tool(
        "web_fetch", {"url": "https://example.com"}, context={})
    assert result.status == ToolResultStatus.CANCELLED
    assert result.content["requires_confirmation"] is True


# ---------- MCP 资源工具 ----------

def _mcp_manager_with_resources() -> MCPManager:
    mgr = MCPManager()
    config = MCPServerConfig(name="fs", transport_type=MCPTransportType.STDIO, command="true")
    mgr._connections["fs"] = MCPServerConnection(
        name="fs", config=config,
        status=MCPServerConnectionStatus.CONNECTED,
        resources=[MCPResource(uri="file:///a.txt", name="a", description="demo")],
    )
    return mgr


async def test_list_mcp_resources(manager):
    for tool in create_mcp_resource_tools(_mcp_manager_with_resources()):
        registry.register(tool)
    result = await manager.execute_tool("list_mcp_resources", {}, context={})
    assert result.status == ToolResultStatus.SUCCESS
    assert result.content["count"] == 1
    assert result.content["resources"][0]["server"] == "fs"


async def test_list_mcp_resources_unknown_server(manager):
    for tool in create_mcp_resource_tools(_mcp_manager_with_resources()):
        registry.register(tool)
    result = await manager.execute_tool(
        "list_mcp_resources", {"server": "nope"}, context={})
    assert result.status == ToolResultStatus.ERROR
    assert "not found" in result.error_message


async def test_read_mcp_resource_unknown_server(manager):
    for tool in create_mcp_resource_tools(_mcp_manager_with_resources()):
        registry.register(tool)
    result = await manager.execute_tool(
        "read_mcp_resource", {"server": "nope", "uri": "file:///a.txt"}, context={})
    assert result.status == ToolResultStatus.ERROR


async def test_platform_refresh_mcp_tools_bridges_deferred_wrapper():
    """Discovered MCP tools join the live scheduling registry but stay deferred."""
    from maestro.bootstrap import build_platform
    from maestro.config import Settings
    from conftest import DATA_DIR, FakeLLM

    platform = build_platform(
        settings=Settings(
            vector_backend="memory", mock_data_dir=DATA_DIR, audit_log_file=None
        ),
        llm=FakeLLM(),
    )
    config = MCPServerConfig(name="demo", transport_type=MCPTransportType.STDIO, command="true")
    platform.mcp.mcp_manager._connections["demo"] = MCPServerConnection(
        name="demo",
        config=config,
        status=MCPServerConnectionStatus.CONNECTED,
        tools=[MCPTool("lookup", "Lookup demo data", {"type": "object"}, "demo")],
    )

    await platform.refresh_mcp_tools()

    name = "mcp__demo__lookup"
    assert platform.tools.get(name).should_defer is True
    assert name in platform.scheduling_engine._agent._allowed


# ---------- foundation 桥接 ----------

from pathlib import Path

from maestro.foundation.tools.registry import ToolRegistry as FoundationRegistry
from maestro.skills.parser import parse_skill_md, validate_allowed_tools
from maestro.tools.bridge import register_framework_tools


async def test_bridge_readonly_tool_executes():
    foundation = FoundationRegistry()
    bridged = register_framework_tools(foundation)
    assert "glob" in bridged and foundation.get("glob").kind == "read"
    result = await foundation.execute("glob", {"pattern": "*.toml"})
    assert "pyproject.toml" in result["filenames"]


async def test_bridge_uses_its_explicit_framework_registry():
    framework = initialize_tools(FrameworkRegistry())
    framework.register(_make_deferred_tool("platform_only", "隔离工具", "platform-only"))
    foundation = FoundationRegistry()
    register_framework_tools(foundation, framework_tools=framework)

    result = await foundation.execute("tool_search", {"query": "+platform-only"})
    assert [item["name"] for item in result["matches"]] == ["platform_only"]


async def test_bridge_write_tool_blocked_by_permission(tmp_path):
    foundation = FoundationRegistry()
    register_framework_tools(foundation)
    assert foundation.get("write_file").kind == "write"
    result = await foundation.execute(
        "write_file", {"file_path": "data/probe.txt", "content": "x"})
    assert result["blocked_by_permission"] is True
    assert "confirmation_id" in result


async def test_bridge_with_gate_creates_pending_and_executes_on_confirm(tmp_path, monkeypatch):
    """带 gate 桥接: 写工具拦截 → PendingAction 入待确认队列 → 批准后真正执行。"""
    from maestro.foundation.audit import AuditLog
    from maestro.foundation.authz import ActionGate, AuthZ, PendingActionStore

    # 把文件工具的根目录指到 tmp_path，避免测试写入项目树
    monkeypatch.setattr(
        "maestro.tools.builtins.filesystem.project_root", lambda: tmp_path)

    pending = PendingActionStore()
    gate = ActionGate(AuthZ(), pending, AuditLog(tmp_path / "audit.jsonl"))
    foundation = FoundationRegistry()
    register_framework_tools(foundation, gate=gate)

    result = await foundation.execute(
        "write_file", {"file_path": "probe.txt", "content": "hello"})
    assert result["blocked_by_permission"] is True
    action_id = result["action_id"]
    assert pending.get(action_id) is not None
    assert not (tmp_path / "probe.txt").exists()  # 确认前不落盘

    action, outcome = await gate.confirm(action_id, approved=True)
    assert action.status == "executed" and outcome.success
    assert (tmp_path / "probe.txt").read_text(encoding="utf-8") == "hello"


async def test_bridge_with_gate_reject_does_not_execute(tmp_path, monkeypatch):
    from maestro.foundation.audit import AuditLog
    from maestro.foundation.authz import ActionGate, AuthZ, PendingActionStore

    monkeypatch.setattr(
        "maestro.tools.builtins.filesystem.project_root", lambda: tmp_path)
    pending = PendingActionStore()
    gate = ActionGate(AuthZ(), pending, AuditLog(tmp_path / "audit.jsonl"))
    foundation = FoundationRegistry()
    register_framework_tools(foundation, gate=gate)

    result = await foundation.execute(
        "write_file", {"file_path": "probe.txt", "content": "hello"})
    action, outcome = await gate.confirm(result["action_id"], approved=False)
    assert action.status == "rejected" and outcome is None
    assert not (tmp_path / "probe.txt").exists()


def test_tool_inspector_skill_validates_against_bridged_registry():
    """演示技能 tool-inspector.md 的 allowed_tools 必须全部是桥接后合法的工具名。"""
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "features" / "demo-skills" / "tool-inspector.md"
    )
    fm, body = parse_skill_md(skill_path.read_text(encoding="utf-8"))
    foundation = FoundationRegistry()
    register_framework_tools(foundation)
    allowed = validate_allowed_tools(
        fm, registered=set(foundation.names()), default=[], named=set())
    assert set(allowed) == {"todo_write", "glob", "read_file", "tool_search", "write_file"}
    assert body.strip()
