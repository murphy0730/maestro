"""调度引擎数据模型。"""

from typing import Literal

from pydantic import BaseModel, Field

from scheduling_platform.domain.models import PendingAction


class ExpediteMessage(BaseModel):
    """LLM 生成的催料文案 (结构化)。"""

    recipient: str
    channel: str = "im"
    content: str


class ExpediteRecord(BaseModel):
    """单条催料记录 (闭环跟踪用)。"""

    material_id: str
    material_name: str = ""
    wo_id: str
    stage: str = ""  # 归因: purchasing_in_transit / quality_inspection / occupied
    target_type: Literal["supplier", "internal"] = "internal"
    recipient: str = ""
    status: Literal["sent", "pending_confirmation", "failed", "denied"] = "sent"
    content: str = ""
    action_id: str | None = None


class ExpeditingOutcome(BaseModel):
    records: list[ExpediteRecord] = Field(default_factory=list)
    pending_actions: list[PendingAction] = Field(default_factory=list)


class DispatchOutcome(BaseModel):
    """下发结果: 待确认的 + 被拦截的 (含原因)。"""

    pending_actions: list[PendingAction] = Field(default_factory=list)
    blocked: list[dict] = Field(default_factory=list)  # [{wo_id, reasons}]


class ExceptionAssessment(BaseModel):
    """异常分类与定级 (LLM/规则)。"""

    type: Literal["equipment", "material", "quality", "personnel", "process"]
    severity: Literal["low", "medium", "high", "critical"]
    reason: str = ""
