"""事件层测试: 事件注入自动唤醒调度引擎 (示例 C) / 巡检主动产生缺料预警。"""

from conftest import FakeLLM

from scheduling_platform.bootstrap import build_platform
from scheduling_platform.domain.models import SystemEvent


async def test_shortage_event_wakes_scheduling_engine(settings):
    """注入缺料事件 → 调度引擎自动唤醒 → 齐套+催料 → 审计可见。"""
    platform = build_platform(settings=settings, llm=FakeLLM())
    event = SystemEvent(type="material_shortage_warning", payload={"wo_id": "WO-123"})
    await platform.bus.publish(event)
    await platform.bus.drain()

    # 引擎被唤醒并审计
    assert platform.audit.query(action="engine_wakeup:material_shortage_warning")
    # WO-123 (O003) 缺 M-002 → 供应商催料 → 进入待确认清单
    pending = platform.pending.list_pending()
    assert any(a.action_type == "send_expedite_message.supplier" for a in pending)


async def test_equipment_alarm_routes_to_exception(settings):
    platform = build_platform(settings=settings, llm=FakeLLM())
    event = SystemEvent(
        type="equipment_alarm",
        payload={"description": "注塑2号线 压力异常报警", "affected_wo_ids": ["WO-102"]},
    )
    await platform.bus.publish(event)
    await platform.bus.drain()
    assert platform.audit.query(action="exception_handled")


async def test_patrol_generates_shortage_warnings(settings):
    """巡检: 拉取适配器预置事件 + 预测性齐套扫描产生缺料预警。"""
    platform = build_platform(settings=settings, llm=FakeLLM())
    await platform.patrol.tick()
    await platform.bus.drain()

    # 预置 equipment_alarm 被拉取处理
    assert platform.audit.query(action="engine_wakeup:equipment_alarm")
    # 缺料任务令 (WO-101/102/103/123 计划开工日在前瞻窗口内) 被主动预警并触发催料
    assert platform.audit.query(action="engine_wakeup:material_shortage_warning")
    assert platform.pending.list_pending() or platform.adapter.outbox

    # 同一任务令不重复告警
    warned_before = set(platform.patrol._warned_wo_ids)
    await platform.patrol.tick()
    assert platform.patrol._warned_wo_ids == warned_before
