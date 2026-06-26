"""路由与统一入口相关数据模型。"""

from typing import Literal

from pydantic import BaseModel, Field

from scheduling_platform.domain.models import PendingAction


class RouteStep(BaseModel):
    """TODO(v0.2): 复合任务拆解的单步 (如「重排+下发」)。"""

    intent: str
    instruction: str


class RouteDecision(BaseModel):
    intent: Literal["planning", "scheduling", "query", "ambiguous"]
    confidence: float  # 0~1
    entities: dict = Field(default_factory=dict)  # 产线/订单/任务令等关键实体
    reason: str = ""  # 判定理由 (用于日志和解释)
    route_method: Literal["embedding", "llm", "clarified", "fallback"] = "llm"
    steps: list[RouteStep] | None = None  # TODO(v0.2): 复合任务


class ChatResponse(BaseModel):
    """统一对话入口的响应。"""

    reply: str
    route: RouteDecision | None = None
    pending_actions: list[PendingAction] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    needs_clarification: bool = False
    options: list[str] = Field(default_factory=list)
