"""排产引擎数据模型。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from maestro.domain.models import Order, ProductionLine


class PlanningRequest(BaseModel):
    """结构化排产请求 (由 extractor 从自然语言抽取)。"""

    order_ids: list[str] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)
    product_line: str | None = None  # 产品线 (用于选策略)
    scenario: str | None = None  # 场景特征 (如"保质期敏感"/"换型频繁")
    objective: str | None = None  # 可选，策略可有默认目标
    locked_assignments: list[dict] = Field(default_factory=list)  # 用户锁定项 (迭代用)
    excluded_lines: list[str] = Field(default_factory=list)  # 不可用产线


class PlanningData(BaseModel):
    """策略求解所需的输入数据快照。"""

    orders: list[Order]
    lines: list[ProductionLine]
    today: date


class Assignment(BaseModel):
    """单个订单的排产结果。"""

    order_id: str
    product_id: str
    line_id: str
    start_date: date
    end_date: date
    due_date: date
    tardiness_days: int = 0


class PlanningResult(BaseModel):
    strategy_name: str = ""
    status: Literal["optimal", "feasible", "infeasible", "error"]
    assignments: list[Assignment] = Field(default_factory=list)
    objective_value: float | None = None
    infeasible_reason: str | None = None
    kpis: dict = Field(default_factory=dict)


class ValidationReport(BaseModel):
    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class StrategySelection(BaseModel):
    """LLM 辅助选择策略的结构化输出。"""

    strategy_name: str
    confidence: float
    reason: str = ""


class SelectionOutcome(BaseModel):
    """策略选择层的最终结论。"""

    strategy_name: str | None = None
    method: Literal["rule", "llm", "none"] = "none"
    confidence: float = 0.0
    reason: str = ""
    needs_clarification: bool = False
    candidates: list[str] = Field(default_factory=list)
