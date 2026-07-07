"""事件层测试 (v0.2)。

事件不再硬映射固定流程，而是被翻译成任务描述唤醒调度引擎的 ReAct 智能体。
- 无 LLM: 引擎仍被唤醒并审计 (engine_wakeup)，降级给齐套总览。
- 有 LLM (脚本): 事件驱动智能体查齐套→催料，产生待确认动作。
- 巡检: 拉取适配器预置事件 + 预测性齐套扫描产生缺料预警，唤醒引擎且不重复告警。
"""

from conftest import FakeLLM

from maestro.bootstrap import build_platform
from maestro.domain.models import SystemEvent


async def test_shortage_event_wakes_scheduling_engine(settings):
    platform = build_platform(settings=settings, llm=FakeLLM())
    await platform.bus.publish(
        SystemEvent(type="material_shortage_warning", payload={"wo_id": "WO-123"})
    )
    await platform.bus.drain()
    assert platform.audit.query(action="engine_wakeup:material_shortage_warning")


async def test_equipment_alarm_wakes_scheduling_engine(settings):
    platform = build_platform(settings=settings, llm=FakeLLM())
    await platform.bus.publish(
        SystemEvent(
            type="equipment_alarm",
            payload={"description": "注塑2号线 压力异常报警", "affected_wo_ids": ["WO-102"]},
        )
    )
    await platform.bus.drain()
    assert platform.audit.query(action="engine_wakeup:equipment_alarm")


async def test_event_drives_react_expedite(settings):
    """脚本化 LLM: 缺料事件唤醒智能体 → 查齐套 → 供应商催料 → 进待确认。"""
    llm = FakeLLM(
        chat_script=[
            [("check_kitting", {"wo_ids": ["WO-123"]})],
            [(
                "send_expedite_message",
                {
                    "recipient": "供应商A",
                    "content": "请加急 M-002",
                    "recipient_type": "supplier",
                    "material_id": "M-002",
                },
            )],
            "已对 WO-123 缺料发起供应商催料，待确认。",
        ]
    )
    platform = build_platform(settings=settings, llm=llm)
    await platform.bus.publish(
        SystemEvent(type="material_shortage_warning", payload={"wo_id": "WO-123"})
    )
    await platform.bus.drain()
    assert platform.audit.query(action="engine_wakeup:material_shortage_warning")
    assert any(
        a.action_type == "send_expedite_message.supplier"
        for a in platform.pending.list_pending()
    )


async def test_patrol_generates_shortage_warnings(settings):
    platform = build_platform(settings=settings, llm=FakeLLM())
    await platform.patrol.tick()
    await platform.bus.drain()

    # 预置 equipment_alarm 被拉取并唤醒引擎
    assert platform.audit.query(action="engine_wakeup:equipment_alarm")
    # 预测性齐套扫描主动产生缺料预警并唤醒引擎
    assert platform.audit.query(action="engine_wakeup:material_shortage_warning")

    # 同一任务令不重复告警
    warned_before = set(platform.patrol._warned_wo_ids)
    await platform.patrol.tick()
    assert platform.patrol._warned_wo_ids == warned_before
