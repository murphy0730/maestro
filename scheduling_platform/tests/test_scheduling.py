"""调度引擎 (v0.2 ReAct) 测试。

覆盖: 齐套底座 / 两道写护栏的「前置断言」(下发齐套校验、催料防重复+缺料核实) /
ReAct 智能体编排 (工具调用 → 护栏拦截 → 待确认动作收集) / LLM 不可用降级。
授权 (ActionGate) 的分级与确认在 builtin 工具内复用，已由前置断言之后的闸口兜底。
"""

from conftest import FakeLLM

from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.engines.scheduling.engine import SCHEDULING_SYSTEM, SchedulingEngine
from scheduling_platform.engines.scheduling.preconditions import (
    make_dispatch_precondition,
    make_expedite_precondition,
)
from scheduling_platform.foundation.kitting import KittingService
from scheduling_platform.foundation.tools.builtin import (
    SCHEDULING_TOOLS,
    FollowupStore,
    register_builtin_tools,
)
from scheduling_platform.foundation.tools.registry import ToolRegistry


def _assemble(adapter, audit, gate, llm, settings):
    """装配一套与 bootstrap 一致的调度引擎 (工具 + 护栏 + ReAct)。"""
    kitting = KittingService(adapter, audit)
    followups = FollowupStore()
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, kitting, llm, followups)
    tools.attach_precondition("dispatch_work_order", make_dispatch_precondition(kitting, adapter))
    tools.attach_precondition(
        "send_expedite_message", make_expedite_precondition(kitting, followups)
    )
    agent = AgentLoop(
        llm, tools, gate.pending, audit, SCHEDULING_SYSTEM, SCHEDULING_TOOLS,
        settings.react_max_steps,
    )
    engine = SchedulingEngine(agent, kitting, audit)
    return kitting, followups, tools, agent, engine


# ── 齐套底座 ────────────────────────────────────────────────


async def test_kitting_check(adapter, audit):
    kitting = KittingService(adapter, audit)
    results = {r.wo_id: r for r in await kitting.check()}
    assert results["WO-104"].is_kitted
    wo101 = results["WO-101"]
    assert not wo101.is_kitted
    shortage = next(s for s in wo101.shortages if s.material_id == "M-002")
    assert shortage.shortage_qty == 300
    assert wo101.estimated_ready_date is not None


# ── 写护栏 1: 前置断言 ──────────────────────────────────────


async def test_dispatch_precondition(adapter, audit):
    kitting = KittingService(adapter, audit)
    precond = make_dispatch_precondition(kitting, adapter)
    # WO-101 缺料 → 不可下发
    blocked = await precond({"wo_id": "WO-101"})
    assert not blocked.ok and "未齐套" in blocked.reason
    # WO-104 齐套 + 产线可用 → 通过
    assert (await precond({"wo_id": "WO-104"})).ok


async def test_expedite_precondition_dedup_and_shortage(adapter, audit):
    kitting = KittingService(adapter, audit)
    followups = FollowupStore()
    precond = make_expedite_precondition(kitting, followups)
    # M-002 确实缺料且未催过 → 通过
    assert (await precond({"material_id": "M-002"})).ok
    # 标记已催 → 再催被拦 (防重复催)
    followups.mark_expedited("M-002")
    dup = await precond({"material_id": "M-002"})
    assert not dup.ok and "重复" in dup.reason
    # 不缺料的物料 → 拦截
    not_short = await precond({"material_id": "M-006"})
    assert not not_short.ok and "不缺料" in not_short.reason


# ── ReAct 智能体编排 ────────────────────────────────────────


async def test_agent_expedite_collects_pending(adapter, audit, gate, settings):
    """智能体: 查齐套 → 向供应商催料 (需确认) → 收口；待确认动作被收集。"""
    llm = FakeLLM(
        chat_script=[
            [("check_kitting", {"wo_ids": ["WO-101"]})],
            [(
                "send_expedite_message",
                {
                    "recipient": "供应商A",
                    "content": "请加急 M-002",
                    "recipient_type": "supplier",
                    "material_id": "M-002",
                },
            )],
            "已对 WO-101 缺料 M-002 发起供应商催料，待你确认后发送。",
        ]
    )
    _, _, _, _, engine = _assemble(adapter, audit, gate, llm, settings)
    resp = await engine.handle_chat("WO-101 缺料帮我催一下", {}, "s1")

    # 供应商催料是 requires_confirmation → 产生 1 个待确认动作
    assert len(resp.pending_actions) == 1
    assert resp.pending_actions[0].action_type == "send_expedite_message.supplier"
    assert audit.query(action="send_expedite_message.supplier")
    # 轨迹里两步工具调用都未被护栏拦截
    assert all(not s["blocked"] for s in resp.data["steps"])


async def test_agent_dispatch_precondition_guardrail(adapter, audit, gate, settings):
    """智能体下发: 未齐套被前置断言拦截 (不产生动作)，齐套的才进待确认。"""
    llm = FakeLLM(
        chat_script=[
            [("dispatch_work_order", {"wo_id": "WO-101"})],  # 缺料 → 拦截
            [("dispatch_work_order", {"wo_id": "WO-104"})],  # 齐套 → 待确认
            "WO-101 缺料未下发；WO-104 已生成下发待确认。",
        ]
    )
    _, _, _, _, engine = _assemble(adapter, audit, gate, llm, settings)
    resp = await engine.handle_chat("把 WO-101 和 WO-104 下发了", {}, "s1")

    steps = resp.data["steps"]
    assert steps[0]["blocked"] is True and "未齐套" in steps[0]["observation"]["blocked"]
    # 只有 WO-104 进了待确认
    assert len(resp.pending_actions) == 1
    assert resp.pending_actions[0].params["wo_id"] == "WO-104"
    assert audit.query(action="precondition_blocked:dispatch_work_order")


async def test_agent_tool_whitelist(adapter, audit, gate, settings):
    """调用白名单外的工具被拒绝 (循环护栏)。"""
    llm = FakeLLM(
        chat_script=[
            [("delete_everything", {})],
            "无法执行该操作。",
        ]
    )
    _, _, _, _, engine = _assemble(adapter, audit, gate, llm, settings)
    resp = await engine.handle_chat("删库", {}, "s1")
    assert resp.data["steps"][0]["blocked"] is True
    assert "白名单" in resp.data["steps"][0]["observation"]["blocked"]


# ── 多轮记忆 ────────────────────────────────────────────────


async def test_agent_receives_multi_turn_history(adapter, audit, gate, settings):
    """多轮: handle_chat 传入的 history 被注入 ReAct 初始 messages (历史在前、本轮在末)。"""
    llm = FakeLLM(chat_script=["结论"])
    captured: dict = {}
    orig = llm.chat_turn

    async def spy(system, messages, tools=None):
        captured.setdefault("messages", list(messages))
        return await orig(system, messages, tools=tools)

    llm.chat_turn = spy  # type: ignore[method-assign]
    _, _, _, _, engine = _assemble(adapter, audit, gate, llm, settings)

    history = [
        {"role": "user", "content": "WO-101 缺什么料"},
        {"role": "assistant", "content": "缺 M-002"},
    ]
    await engine.handle_chat("帮我催一下这个料", {}, "s1", history=history)

    msgs = captured["messages"]
    assert [m["content"] for m in msgs[:2]] == ["WO-101 缺什么料", "缺 M-002"]  # 历史在前
    assert msgs[-1] == {"role": "user", "content": "帮我催一下这个料"}  # 本轮在末


# ── 降级 ────────────────────────────────────────────────────


async def test_engine_degraded_without_llm(adapter, audit, gate, settings):
    """LLM 不可用 → 确定性齐套总览 (不臆造动作)。"""
    engine = _assemble(adapter, audit, gate, FakeLLM(), settings)[4]
    resp = await engine.handle_chat("齐套情况", {}, "s1")
    assert "齐套" in resp.reply
    assert not resp.pending_actions


async def test_agent_progress_reporting(adapter, audit, gate, settings):
    """on_progress 在思考/工具步实时上报 (SSE progress 帧数据源)。"""
    llm = FakeLLM(chat_script=[[("check_kitting", {"wo_ids": ["WO-104"]})], "WO-104 已齐套。"])
    _, _, _, agent, _ = _assemble(adapter, audit, gate, llm, settings)
    seen: list[str] = []

    async def on_progress(text: str) -> None:
        seen.append(text)

    result = await agent.run("查 WO-104 齐套", on_progress=on_progress)
    assert result.answer == "WO-104 已齐套。"
    assert any("思考中" in t for t in seen)
    assert any("check_kitting" in t for t in seen)
