"""Engine 抽象基类与统一响应模型。

引擎隔离原则: 排产与调度引擎互不直接 import 对方内部类，只通过共享底座交互。
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from scheduling_platform.domain.models import PendingAction


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
        self, message: str, entities: dict, session_id: str, history: list[dict] | None = None
    ) -> EngineResponse:
        """处理一条经 Orchestrator 路由进来的用户消息。

        `history` 为该会话此前的 user/assistant 文本轮次 (不含本条)，供需要多轮
        上下文的引擎 (如调度 ReAct) 使用；固定工作流引擎可忽略。
        """
