"""Engine 抽象基类与统一响应模型。

引擎隔离原则: 排产与调度引擎互不直接 import 对方内部类，只通过共享底座交互。
"""

import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from scheduling_platform.domain.models import PendingAction

logger = logging.getLogger(__name__)

# 引擎执行中的进度上报回调 (SSE progress 帧的数据源)。None = 调用方不关心进度。
ProgressFn = Callable[[str], Awaitable[None]]


async def emit_progress(cb: ProgressFn | None, text: str) -> None:
    """安全上报进度: 回调缺席时跳过，回调抛错只记日志、绝不影响主流程。"""
    if cb is None:
        return
    try:
        await cb(text)
    except Exception:  # noqa: BLE001 — 进度是旁路
        logger.debug("进度上报失败 (忽略): %s", text, exc_info=True)


class EngineResponse(BaseModel):
    """引擎处理结果的统一载体。"""

    reply: str
    data: dict = Field(default_factory=dict)
    pending_actions: list[PendingAction] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_options: list[str] = Field(default_factory=list)


class Engine(ABC):
    """对话驱动引擎的抽象基类。"""

    name: str = ""

    @abstractmethod
    async def handle_chat(
        self,
        message: str,
        entities: dict,
        session_id: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> EngineResponse:
        """处理一条经 Orchestrator 路由进来的用户消息。

        `history` 为该会话此前的 user/assistant 文本轮次 (不含本条)，供需要多轮
        上下文的引擎 (如调度 ReAct) 使用；固定工作流引擎可忽略。
        `on_progress` 用于长任务执行中上报阶段进度 (SSE progress 帧)。
        """
