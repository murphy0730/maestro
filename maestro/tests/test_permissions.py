"""执行模式 (plan/auto) × 权限门。

覆盖两件事:
1. 写生产系统的动作，任何模式下都需人工确认；deny 规则可收紧，allow 规则不能降级。
2. 非生产写入 (文件/网络) 在完全访问模式下直接执行，默认模式下挂起待确认。
"""

import asyncio
from datetime import timedelta

import pytest

from maestro.domain.models import ActionResult
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import ActionGate, AuthZ, PendingActionStore
from maestro.foundation.exec_context import current_mode, use_mode
from maestro.foundation.kitting import KittingService
from maestro.foundation.permissions import (
    PRODUCTION_WRITE_ACTIONS,
    PermissionEngine,
    PermissionRule,
)
from maestro.foundation.tools.builtin import (
    FollowupStore,
    register_builtin_tools,
    scheduling_tools,
)
from maestro.foundation.tools.registry import ToolRegistry

# 桥接工具经 bridge.py 以 "tool:<name>" 作为 action_type 送进 ActionGate
NON_PRODUCTION_ACTIONS = ["tool:write_file", "tool:edit_file", "tool:web_fetch"]


def _registry(adapter, audit) -> tuple[ToolRegistry, ActionGate]:
    gate = ActionGate(AuthZ(), PendingActionStore(), AuditLog(file_path=None))
    tools = ToolRegistry()
    register_builtin_tools(
        tools, adapter, gate, KittingService(adapter, audit), None, FollowupStore()
    )
    return tools, gate


# ── 执行模式载体 ────────────────────────────────────────────


def test_mode_defaults_to_plan_and_restores():
    """默认 plan (故障安全: 事件驱动/CLI 不经 HTTP，写操作照旧需确认)。"""
    assert current_mode() == "plan"
    with use_mode("auto"):
        assert current_mode() == "auto"
    assert current_mode() == "plan"


# ── 生产写入: 模式无关 ──────────────────────────────────────


@pytest.mark.parametrize("action_type", sorted(PRODUCTION_WRITE_ACTIONS))
@pytest.mark.parametrize("mode", ["plan", "auto"])
def test_production_writes_always_ask(action_type, mode):
    assert PermissionEngine().evaluate_action(action_type, mode).effect == "ask"


def test_allow_rule_cannot_downgrade_production_write():
    """注入规则不能把生产写入降级为直接执行。"""
    engine = PermissionEngine(
        rules=[PermissionRule(effect="allow", action_type="dispatch_work_order")]
    )
    assert engine.evaluate_action("dispatch_work_order", "auto").effect == "ask"


def test_deny_rule_can_tighten_production_write():
    """反向: deny 是收紧，仍然生效。"""
    engine = PermissionEngine(
        rules=[PermissionRule(effect="deny", action_type="dispatch_work_order")]
    )
    assert engine.evaluate_action("dispatch_work_order", "auto").effect == "deny"


# ── 非生产写入: 模式相关 ────────────────────────────────────


@pytest.mark.parametrize("action_type", NON_PRODUCTION_ACTIONS)
def test_file_writes_ask_in_plan_mode(action_type):
    assert PermissionEngine().evaluate_action(action_type, "plan").effect == "ask"


@pytest.mark.parametrize("action_type", NON_PRODUCTION_ACTIONS)
def test_file_writes_allowed_in_auto_mode(action_type):
    assert PermissionEngine().evaluate_action(action_type, "auto").effect == "allow"


# ── 端到端: ActionGate 经 contextvar 读取模式 ───────────────


async def _request(gate: ActionGate, action_type: str):
    async def _execute() -> ActionResult:
        return ActionResult(success=True, action=action_type, detail="done")

    return await gate.request(action_type, description=action_type, executor=_execute)


async def test_gate_executes_file_write_in_auto_mode(gate):
    with use_mode("auto"):
        outcome = await _request(gate, "tool:write_file")
    assert outcome.status == "executed"
    assert not gate.pending.list_pending()


async def test_gate_suspends_file_write_in_plan_mode(gate):
    with use_mode("plan"):
        outcome = await _request(gate, "tool:write_file")
    assert outcome.status == "pending"
    assert len(gate.pending.list_pending()) == 1


async def test_gate_suspends_mes_write_even_in_auto_mode(gate):
    """完全访问模式放开文件写，但绝不放开写生产系统。"""
    with use_mode("auto"):
        outcome = await _request(gate, "dispatch_work_order")
    assert outcome.status == "pending"
    assert len(gate.pending.list_pending()) == 1


async def test_confirm_within_window_does_not_revalidate(gate):
    called = 0

    async def revalidate(_params):
        nonlocal called
        called += 1
        return False, "should not run"

    gate.register_revalidator("dispatch_work_order", revalidate)
    outcome = await _request(gate, "dispatch_work_order")
    action, result = await gate.confirm(outcome.action.action_id, True)
    assert action.status == "executed" and result.success
    assert called == 0


async def test_confirm_after_window_revalidates(gate):
    async def revalidate(_params):
        return False, "工单状态已变化"

    gate.register_revalidator("dispatch_work_order", revalidate)
    outcome = await _request(gate, "dispatch_work_order")
    outcome.action.validated_at -= timedelta(seconds=gate.revalidation_seconds)
    action, result = await gate.confirm(outcome.action.action_id, True)
    assert result is None
    assert action.status == "validation_failed"
    assert action.failure_reason == "工单状态已变化"


async def test_confirm_after_expiration_is_rejected(gate):
    outcome = await _request(gate, "dispatch_work_order")
    outcome.action.validated_at -= timedelta(seconds=gate.expiration_seconds)
    action, result = await gate.confirm(outcome.action.action_id, True)
    assert result is None
    assert action.status == "expired"


async def test_concurrent_confirm_executes_once(gate):
    executions = 0

    async def execute():
        nonlocal executions
        executions += 1
        await asyncio.sleep(0)
        return ActionResult(success=True, action="dispatch_work_order")

    outcome = await gate.request(
        "dispatch_work_order", "dispatch", executor=execute
    )
    results = await asyncio.gather(
        gate.confirm(outcome.action.action_id, True),
        gate.confirm(outcome.action.action_id, True),
        return_exceptions=True,
    )
    assert executions == 1
    assert sum(isinstance(item, ValueError) for item in results) == 1


async def test_pending_action_survives_restart(tmp_path):
    db = tmp_path / "pending.db"
    first = ActionGate(AuthZ(), PendingActionStore(db), AuditLog(file_path=None))
    first.register_executor(
        "dispatch_work_order",
        lambda params: _persisted_result(params),
    )
    outcome = await first.request(
        "dispatch_work_order", "dispatch", params={"wo_id": "WO-1"}
    )

    restarted = ActionGate(AuthZ(), PendingActionStore(db), AuditLog(file_path=None))
    restarted.register_executor(
        "dispatch_work_order",
        lambda params: _persisted_result(params),
    )
    restored = restarted.pending.get(outcome.action.action_id)
    assert restored is not None and restored.params == {"wo_id": "WO-1"}
    action, result = await restarted.confirm(restored.action_id, True)
    assert action.status == "executed" and result.detail == "WO-1"


async def _persisted_result(params):
    return ActionResult(
        success=True, action="dispatch_work_order", detail=params["wo_id"]
    )


def test_deny_rule_wins_regardless_of_declaration_order():
    engine = PermissionEngine(rules=[
        PermissionRule(effect="allow", action_type="tool:write_file"),
        PermissionRule(effect="deny", action_type="tool:write_file"),
    ])
    assert engine.evaluate_action("tool:write_file").effect == "deny"


# ── 动态白名单 ──────────────────────────────────────────────


def test_scheduling_whitelist_picks_up_newly_registered_tool(adapter, audit):
    """新增内置工具只要注册进 registry 就自动可被调度引擎调用，无需改白名单。"""
    tools, _ = _registry(adapter, audit)

    async def _probe() -> dict:
        return {"ok": True}

    tools.register("probe_tool", "探针", {"type": "object", "properties": {}}, _probe, kind="read")

    allowed = scheduling_tools(tools)
    assert "probe_tool" in allowed
    exported = {t["function"]["name"] for t in tools.to_openai_tools(allowed)}
    assert "probe_tool" in exported


def test_record_followup_is_a_gated_write(adapter, audit):
    """record_followup 现为 write，经 ActionGate 判级 (用户要求: 任何模式都需确认)。"""
    tools, gate = _registry(adapter, audit)
    assert tools.get("record_followup").kind == "write"


# ── 桥接工具真实落盘: 框架权限门 + ActionGate 两道闸的合流 ──


@pytest.fixture
def bridged(monkeypatch, tmp_path, audit):
    """把 tools/ 框架工具桥进一个干净的 foundation registry，文件根重定向到 tmp。"""
    from maestro.tools import initialize_tools
    from maestro.tools.bridge import register_framework_tools
    import maestro.tools.builtins.filesystem as fs

    monkeypatch.setattr(fs, "project_root", lambda: tmp_path)
    gate = ActionGate(AuthZ(), PendingActionStore(), audit)
    tools = ToolRegistry()
    initialize_tools()
    register_framework_tools(tools, gate=gate)
    return tools, gate, tmp_path


async def test_write_file_lands_on_disk_in_auto_mode(bridged):
    """完全访问模式: 框架权限门要确认 → ActionGate 判 allow → 立即执行，文件真的写了。"""
    tools, gate, root = bridged
    with use_mode("auto"):
        result = await tools.execute("write_file", {"file_path": "note.txt", "content": "hi"})
    assert not isinstance(result, dict) or not result.get("blocked_by_permission")
    assert (root / "note.txt").read_text(encoding="utf-8") == "hi"
    assert not gate.pending.list_pending()


async def test_write_file_suspended_in_plan_mode(bridged):
    """默认模式: 落到 ActionGate 挂起，文件没写。"""
    tools, gate, root = bridged
    with use_mode("plan"):
        result = await tools.execute("write_file", {"file_path": "note.txt", "content": "hi"})
    assert result["blocked_by_permission"] is True
    assert not (root / "note.txt").exists()
    pending = gate.pending.list_pending()
    assert len(pending) == 1 and pending[0].action_type == "tool:write_file"


async def test_read_file_never_asks(bridged):
    """读操作在两种模式下都直接执行，不经 ActionGate。"""
    tools, gate, root = bridged
    (root / "a.txt").write_text("hello", encoding="utf-8")
    for mode in ("plan", "auto"):
        with use_mode(mode):
            result = await tools.execute("read_file", {"file_path": "a.txt"})
        assert "hello" in str(result)
    assert not gate.pending.list_pending()
