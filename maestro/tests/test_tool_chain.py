"""工具调用链 5 项增强能力的验收测试 (对齐 Claude Code)。

覆盖: ①泛型输入校验 ②实时进度回调 ③多工具并发 ④交互式权限确认 ⑤独立规则权限引擎。
每项一条最小验收，且不破坏既有护栏 (白名单/去重/写后清读/8KB 截断/ActionGate)。
"""

import asyncio

from pydantic import BaseModel

from conftest import FakeLLM

from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.foundation.permissions import PermissionEngine, PermissionRule
from maestro.foundation.tools.registry import ToolRegistry
from maestro.foundation.tools.validation import validate_arguments
from maestro.tools import ToolRegistry as FrameworkRegistry, initialize_tools
from maestro.tools.base import ToolDef, ToolResult, ToolResultStatus, build_tool
from maestro.tools.bridge import register_framework_tools


class _NoArgs(BaseModel):
    pass


def _loop(llm, tools, gate, audit, allowed, **kw) -> AgentLoop:
    return AgentLoop(llm, tools, gate.pending, audit, "", allowed, 8, **kw)


# ── ① 泛型输入校验 ──────────────────────────────────────────


def test_validate_arguments_unit():
    schema = {
        "type": "object",
        "properties": {"wo_id": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["wo_id"],
    }
    assert validate_arguments(schema, {"wo_id": "WO-1", "n": 3}) == (True, "")
    assert not validate_arguments(schema, {"n": 3})[0]  # 缺必填
    assert not validate_arguments(schema, {"wo_id": 123})[0]  # 类型错
    assert validate_arguments(schema, {"wo_id": "WO-1", "n": None})[0]  # None 放行


async def test_agent_invalid_input_blocked(audit, gate):
    """非法参数在执行前被拦截: 返回错误 observation 且工具未被调用。"""
    called = []

    async def strict(wo_id: str):
        called.append(wo_id)
        return {"ok": True}

    tools = ToolRegistry()
    tools.register(
        "strict",
        "需要字符串 wo_id",
        {"type": "object", "properties": {"wo_id": {"type": "string"}}, "required": ["wo_id"]},
        strict,
        kind="read",
    )
    llm = FakeLLM(chat_script=[[("strict", {"wo_id": 123})], "结论"])  # wo_id 传成 int
    result = await _loop(llm, tools, gate, audit, ["strict"]).run("t")

    step = result.steps[0]
    assert step.blocked is True
    assert "输入校验失败" in step.observation["blocked"]
    assert called == []  # 工具从未执行
    assert audit.query(action="invalid_input:strict")


# ── ② 实时进度回调 ──────────────────────────────────────────


async def test_registry_execute_emits_progress():
    """registry.execute 按阶段 emit started/done, 长任务 handler 可中途上报。"""
    events: list[dict] = []

    async def on_progress(ev: dict) -> None:
        events.append(ev)

    async def long_task(on_progress=None):
        await on_progress({"phase": "progress", "tool": "long_task", "percent": 50})
        return {"ok": True}

    tools = ToolRegistry()
    tools.register("long_task", "长任务", {"type": "object", "properties": {}}, long_task)
    await tools.execute("long_task", {}, on_progress=on_progress)

    phases = [e["phase"] for e in events]
    assert phases == ["started", "progress", "done"]
    assert any(e.get("percent") == 50 for e in events)


async def test_registry_execute_no_progress_backward_compatible():
    """不传 on_progress → 零开销同步执行 (既有调用签名不变)。"""
    async def plain():
        return {"ok": True}

    tools = ToolRegistry()
    tools.register("plain", "普通", {"type": "object", "properties": {}}, plain)
    assert await tools.execute("plain", {}) == {"ok": True}


# ── ③ 多工具并发 ────────────────────────────────────────────


async def test_agent_concurrent_readonly_tools(audit, gate):
    """一轮 3 个独立只读 tool_call → 并发启动 (非严格串行)。"""
    active = 0
    peak = 0

    async def slow():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return {"ok": True}

    tools = ToolRegistry()
    for n in ("r1", "r2", "r3"):
        tools.register(n, "只读", {"type": "object", "properties": {}}, slow, kind="read")
    llm = FakeLLM(chat_script=[[("r1", {}), ("r2", {}), ("r3", {})], "结论"])
    result = await _loop(llm, tools, gate, audit, ["r1", "r2", "r3"]).run("t")

    assert peak >= 2  # 串行执行 peak 恒为 1；并发才会 ≥2
    assert [s.blocked for s in result.steps] == [False, False, False]
    assert result.answer == "结论"


# ── ④ 交互式权限确认 ────────────────────────────────────────


async def test_agent_ask_read_tool_pending_without_resolver(audit, gate):
    """读工具被配置为 'ask' 且无解析器 → 挂起 pending, 不执行。"""
    called = []

    async def read_a():
        called.append(1)
        return {"ok": True}

    tools = ToolRegistry()
    tools.register("read_a", "读", {"type": "object", "properties": {}}, read_a, kind="read")
    engine = PermissionEngine(rules=[PermissionRule(effect="ask", tool="read_a")])
    llm = FakeLLM(chat_script=[[("read_a", {})], "结论"])
    result = await _loop(llm, tools, gate, audit, ["read_a"], permissions=engine).run("t")

    step = result.steps[0]
    assert step.blocked is True
    assert step.observation.get("pending_confirmation") is True
    assert called == []  # 挂起未执行
    assert audit.query(action="permission_pending:read_a")


async def test_agent_ask_resolver_approves_executes(audit, gate):
    """'ask' + 解析器放行 → 正常执行 (交互确认层叠加在写护栏之上, 不改写流程)。"""
    async def read_a():
        return {"ok": True}

    tools = ToolRegistry()
    tools.register("read_a", "读", {"type": "object", "properties": {}}, read_a, kind="read")
    engine = PermissionEngine(rules=[PermissionRule(effect="ask", tool="read_a")])

    async def resolver(name, args, decision):
        return True

    llm = FakeLLM(chat_script=[[("read_a", {})], "结论"])
    result = await _loop(
        llm, tools, gate, audit, ["read_a"], permissions=engine, confirm_resolver=resolver
    ).run("t")
    assert result.steps[0].blocked is False
    assert result.steps[0].observation == {"ok": True}


# ── ⑤ 独立规则权限引擎 ──────────────────────────────────────


async def test_agent_deny_rule_intercepts(audit, gate):
    """新增 deny 规则拒绝某只读工具 → 被拦截, 决策来自统一引擎。"""
    called = []

    async def read_a():
        called.append(1)
        return {"ok": True}

    tools = ToolRegistry()
    tools.register("read_a", "读", {"type": "object", "properties": {}}, read_a, kind="read")
    engine = PermissionEngine(rules=[PermissionRule(effect="deny", tool="read_a", reason="演示拒绝")])
    llm = FakeLLM(chat_script=[[("read_a", {})], "结论"])
    result = await _loop(llm, tools, gate, audit, ["read_a"], permissions=engine).run("t")

    assert result.steps[0].blocked is True
    assert "权限引擎拒绝" in result.steps[0].observation["blocked"]
    assert called == []
    denied = audit.query(action="permission_denied:read_a")
    assert denied and denied[0].result["source"] == "rule"


def test_authz_decision_sourced_from_engine():
    """ActionGate 的 AuthZ.decide 决策改由统一引擎产生 (deny 规则即刻生效)。"""
    from maestro.foundation.authz import AuthZ

    engine = PermissionEngine(rules=[PermissionRule(effect="deny", action_type="dispatch_work_order")])
    authz = AuthZ(engine=engine)
    assert authz.decide("dispatch_work_order") == "deny"  # deny 规则可收紧生产写入
    # 写生产系统: 任何模式都需确认 (internal 催料也不例外)
    assert authz.decide("send_expedite_message.internal") == "requires_confirmation"
    assert authz.decide("send_expedite_message.internal", "auto") == "requires_confirmation"


async def test_deferred_tool_requires_search_before_agent_can_use_it(audit, gate):
    """tool_search activates only returned deferred definitions for one ReAct run."""
    framework = initialize_tools(FrameworkRegistry())

    async def deferred_execute(args, context, on_progress=None):
        return ToolResult(status=ToolResultStatus.SUCCESS, content={"loaded": True})

    framework.register(build_tool(ToolDef(
        name="deferred_probe",
        description="Deferred probe",
        input_schema=_NoArgs,
        execute=deferred_execute,
        should_defer=True,
        search_hint="probe",
    )))
    tools = ToolRegistry()
    register_framework_tools(tools, framework_tools=framework)
    llm = FakeLLM(chat_script=[
        [("tool_search", {"query": "select:deferred_probe"})],
        [("deferred_probe", {})],
        "done",
    ])
    result = await _loop(llm, tools, gate, audit, tools.names()).run("t")

    assert result.steps[0].blocked is False
    assert result.steps[1].observation == {"loaded": True}
