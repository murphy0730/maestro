"""调度引擎测试: 齐套 / 催料分级授权 / 下发拦截与确认 / 异常分诊。"""

from conftest import FakeLLM

from scheduling_platform.domain.models import ProductionException
from scheduling_platform.engines.scheduling.workflows.dispatch import DispatchWorkflow
from scheduling_platform.engines.scheduling.workflows.exception import ExceptionWorkflow
from scheduling_platform.engines.scheduling.workflows.expediting import ExpeditingWorkflow
from scheduling_platform.engines.scheduling.workflows.kitting import KittingWorkflow


async def test_kitting_check(adapter, audit):
    kitting = KittingWorkflow(adapter, audit)
    results = {r.wo_id: r for r in await kitting.check()}
    # WO-104 (O005/P-ASM-01, M-006 充足) 齐套
    assert results["WO-104"].is_kitted
    # WO-101 (O001/P-INJ-01) 缺 M-002: 需 400, 在库 100
    wo101 = results["WO-101"]
    assert not wo101.is_kitted
    shortage = next(s for s in wo101.shortages if s.material_id == "M-002")
    assert shortage.shortage_qty == 300
    # 在途 1200 可覆盖 → 给出预计齐套时间
    assert wo101.estimated_ready_date is not None


async def test_expediting_authz_split(adapter, audit, gate):
    """内部催料 auto 直接发(写 outbox)；供应商催料 requires_confirmation 待确认。"""
    kitting = KittingWorkflow(adapter, audit)
    expediting = ExpeditingWorkflow(adapter, gate, audit, FakeLLM())
    results = await kitting.check(["WO-101", "WO-102"])
    outcome = await expediting.run(results)

    # WO-101 缺 M-002 → 采购在途 → 供应商 → 待确认
    supplier = next(r for r in outcome.records if r.material_id == "M-002")
    assert supplier.target_type == "supplier"
    assert supplier.status == "pending_confirmation"
    assert supplier.action_id is not None
    # WO-102 缺 M-003 → 质检 → 内部 → 自动发送进 outbox
    internal = next(r for r in outcome.records if r.material_id == "M-003")
    assert internal.target_type == "internal"
    assert internal.status == "sent"
    assert any(m["recipient"] == internal.recipient for m in adapter.outbox)
    # 全部写操作进审计
    assert audit.query(action="send_expedite_message")


async def test_dispatch_blocks_unkitted_and_confirms(adapter, audit, gate):
    kitting = KittingWorkflow(adapter, audit)
    dispatch = DispatchWorkflow(adapter, gate, audit, kitting)
    outcome = await dispatch.run(["WO-101", "WO-104"])

    # WO-101 缺料 → 拦截并解释原因
    blocked = next(b for b in outcome.blocked if b["wo_id"] == "WO-101")
    assert any("未齐套" in r for r in blocked["reasons"])
    # WO-104 齐套 → 生成待确认动作 (不直接执行)
    action = next(a for a in outcome.pending_actions if a.params["wo_id"] == "WO-104")
    wo = (await adapter.get_work_orders({"wo_ids": ["WO-104"]}))[0]
    assert wo.status == "draft"
    # 人确认后才真正下发
    resolved, result = await gate.confirm(action.action_id, approved=True)
    assert resolved.status == "executed" and result.success
    wo = (await adapter.get_work_orders({"wo_ids": ["WO-104"]}))[0]
    assert wo.status == "dispatched"


async def test_dispatch_reject_keeps_draft(adapter, audit, gate):
    kitting = KittingWorkflow(adapter, audit)
    dispatch = DispatchWorkflow(adapter, gate, audit, kitting)
    outcome = await dispatch.run(["WO-104"])
    action = outcome.pending_actions[0]
    resolved, result = await gate.confirm(action.action_id, approved=False)
    assert resolved.status == "rejected" and result is None
    wo = (await adapter.get_work_orders({"wo_ids": ["WO-104"]}))[0]
    assert wo.status == "draft"


async def test_exception_triage_keeps_human_in_loop(adapter, audit, gate):
    """异常处置: Agent 给分诊+建议，通知需人确认，不自动执行关键决策。"""
    workflow = ExceptionWorkflow(adapter, gate, audit, FakeLLM())
    exc = ProductionException(
        source="user", description="注塑2号线停机报警", affected_wo_ids=["WO-102"]
    )
    case = await workflow.handle(exc)
    assert case["assessment"]["type"] == "equipment"  # 关键词规则降级
    assert case["affected_work_orders"] == ["WO-102"]
    assert len(case["proposals"]) >= 2
    # 通知是 requires_confirmation 待确认，未直接发送
    assert case["pending_actions"]
    assert not adapter.outbox
    assert audit.query(action="exception_handled")
