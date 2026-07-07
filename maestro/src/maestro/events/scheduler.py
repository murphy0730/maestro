"""定时巡检器。

按固定间隔: ① 调 IntegrationAdapter.poll_events() 拉取系统事件发布到总线;
② 预测性巡检 —— 扫描近期待开工任务令的齐套情况，对「即将因缺料卡住」的
任务令主动产生 material_shortage_warning 事件。
"""

import asyncio
import logging
from datetime import date, timedelta

from maestro.config import Settings
from maestro.domain.models import SystemEvent
from maestro.events.event_bus import EventBus
from maestro.foundation.kitting import KittingService
from maestro.foundation.integration.base import IntegrationAdapter

logger = logging.getLogger(__name__)


class PatrolScheduler:
    def __init__(
        self,
        adapter: IntegrationAdapter,
        bus: EventBus,
        kitting: KittingService,
        settings: Settings,
    ):
        self._adapter = adapter
        self._bus = bus
        self._kitting = kitting
        self._settings = settings
        self._warned_wo_ids: set[str] = set()  # 同一任务令缺料只告警一次

    async def run(self) -> None:
        logger.info(
            "[PATROL] 定时巡检启动 (间隔 %.0fs, 齐套前瞻 %d 天)",
            self._settings.patrol_interval_seconds,
            self._settings.kitting_lookahead_days,
        )
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 — 单次巡检失败不终止循环
                logger.exception("[PATROL] 巡检异常")
            await asyncio.sleep(self._settings.patrol_interval_seconds)

    async def tick(self) -> None:
        """单次巡检 (独立方法便于测试/CLI 手动触发)。"""
        # ① 拉取外部系统事件
        for event in await self._adapter.poll_events():
            await self._bus.publish(event)

        # ② 预测性巡检: 即将开工但缺料的任务令
        work_orders = await self._adapter.get_work_orders({"status": "draft"})
        horizon = date.today() + timedelta(days=self._settings.kitting_lookahead_days)
        upcoming = [
            w for w in work_orders
            if w.planned_start is not None
            and w.planned_start <= horizon
            and w.wo_id not in self._warned_wo_ids
        ]
        if not upcoming:
            return
        for result in await self._kitting.check([w.wo_id for w in upcoming]):
            if result.is_kitted:
                continue
            self._warned_wo_ids.add(result.wo_id)
            await self._bus.publish(
                SystemEvent(
                    type="material_shortage_warning",
                    payload={
                        "wo_id": result.wo_id,
                        "shortages": [s.model_dump() for s in result.shortages],
                        "source": "patrol",
                    },
                )
            )
