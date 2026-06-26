"""内存事件总线 (asyncio.Queue)。

初始版本不引入 Celery/Redis；publish/subscribe 接口保持稳定，
后续可替换为外部消息队列。
"""

import asyncio
import logging
from typing import Awaitable, Callable

from scheduling_platform.domain.models import SystemEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[SystemEvent], Awaitable[None]]


class EventBus:
    def __init__(self):
        self._queue: asyncio.Queue[SystemEvent] = asyncio.Queue()
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅某类事件；event_type="*" 订阅全部。"""
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: SystemEvent) -> None:
        logger.info("[EVENT] publish %s id=%s payload=%s", event.type, event.event_id, event.payload)
        await self._queue.put(event)

    async def dispatch(self, event: SystemEvent) -> None:
        handlers = self._handlers.get(event.type, []) + self._handlers.get("*", [])
        if not handlers:
            logger.warning("[EVENT] 事件 %s 无订阅者", event.type)
        for handler in handlers:
            try:
                await handler(event)
            except Exception:  # noqa: BLE001 — 单个 handler 失败不阻断总线
                logger.exception("[EVENT] handler 处理 %s 失败", event.type)

    async def run(self) -> None:
        """消费循环 (FastAPI 启动时作为后台 task 运行)。"""
        logger.info("[EVENT] 事件总线消费循环启动")
        while True:
            event = await self._queue.get()
            await self.dispatch(event)
            self._queue.task_done()

    async def drain(self) -> None:
        """同步消费完当前队列中的全部事件 (测试/CLI 手动触发用)。"""
        while not self._queue.empty():
            event = self._queue.get_nowait()
            await self.dispatch(event)
            self._queue.task_done()
