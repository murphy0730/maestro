"""核心领域模型 (订单/BOM/产线/物料/任务令...)。

初始版本字段保持精简但可扩展。
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


class Order(BaseModel):
    """生产订单。"""

    order_id: str
    product_id: str
    quantity: int
    due_date: date
    priority: int = 5
    status: str = "open"


class BomItem(BaseModel):
    """物料清单项。"""

    product_id: str
    material_id: str
    material_name: str = ""
    qty_per_unit: float


class ProductionLine(BaseModel):
    """产线。

    `product_line` 为产线所属的产品线类别(如 注塑/SMT贴片)，用于排产策略选择。
    """

    line_id: str
    name: str
    capacity_per_day: int
    available: bool = True
    supported_products: list[str] = Field(default_factory=list)
    product_line: str = ""


class Material(BaseModel):
    """物料。"""

    material_id: str
    name: str
    on_hand_qty: float
    in_transit_qty: float = 0
    unit: str = "pcs"


WorkOrderStatus = Literal["draft", "dispatched", "in_progress", "done", "blocked"]


class WorkOrder(BaseModel):
    """任务令。"""

    wo_id: str
    order_id: str
    line_id: str
    planned_start: date | None = None
    planned_end: date | None = None
    status: WorkOrderStatus = "draft"


class Shortage(BaseModel):
    """单个物料缺口。"""

    material_id: str
    material_name: str = ""
    required_qty: float
    available_qty: float
    shortage_qty: float
    unit: str = "pcs"


class KittingResult(BaseModel):
    """齐套检查结果。"""

    wo_id: str
    is_kitted: bool
    shortages: list[Shortage] = Field(default_factory=list)
    estimated_ready_date: date | None = None


ExceptionType = Literal["equipment", "material", "quality", "personnel", "process"]


class ProductionException(BaseModel):
    """生产异常。"""

    exception_id: str = Field(default_factory=_short_id)
    type: ExceptionType = "process"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    source: str = "user"
    description: str = ""
    affected_wo_ids: list[str] = Field(default_factory=list)
    status: str = "open"


class SystemEvent(BaseModel):
    """系统事件 (事件层流转的统一载体)。"""

    event_id: str = Field(default_factory=_short_id)
    type: str  # material_shortage_warning / equipment_alarm / quality_issue ...
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class ActionResult(BaseModel):
    """写操作的执行结果。"""

    success: bool
    action: str
    detail: str = ""
    ref_id: str | None = None


PendingActionStatus = Literal[
    "pending",
    "executing",
    "rejected",
    "executed",
    "validation_failed",
    "failed",
    "expired",
]


class PendingAction(BaseModel):
    """需人确认的待执行动作。"""

    action_id: str = Field(default_factory=_short_id)
    action_type: str
    description: str
    params: dict = Field(default_factory=dict)
    status: PendingActionStatus = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    validated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    failure_reason: str | None = None
