"""事件 → 调度引擎 的处理器。

映射规则:
- material_shortage_warning → kitting + expediting (引擎内编排)
- equipment_alarm / quality_issue → exception
处理结果中需要人确认的，写入待办 (初始版本: 打印 + 日志 + PendingActionStore)。
"""

import logging

from scheduling_platform.domain.models import SystemEvent
from scheduling_platform.engines.scheduling.engine import SchedulingEngine
from scheduling_platform.events.event_bus import EventBus

logger = logging.getLogger(__name__)


def register_event_handlers(bus: EventBus, engine: SchedulingEngine) -> None:
    async def on_event(event: SystemEvent) -> None:
        response = await engine.handle_event(event)
        # 待办/通知: 初始版本打印 + 写日志 (PendingAction 已入 store, 可经 API 确认)
        logger.info("[TODO-NOTIFY] 事件 %s 处理完成: %s", event.type, response.reply)
        for action in response.pending_actions:
            logger.info(
                "[TODO-NOTIFY] 待人确认动作 [%s] %s", action.action_id, action.description
            )

    bus.subscribe("material_shortage_warning", on_event)
    bus.subscribe("equipment_alarm", on_event)
    bus.subscribe("quality_issue", on_event)
