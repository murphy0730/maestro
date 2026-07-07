"""PlanningStrategy 抽象基类。

核心理念: 不存在「一个排产算法」，只有「一族排产策略」。每种排产场景是一个
可插拔的策略插件，自带建模+约束+算法 (OR-Tools/启发式/规则皆可)，引擎不感知
内部实现。加新产品线 = 新增一个策略类并注册，不动引擎、不动其它策略。
"""

import math
from abc import ABC, abstractmethod

from maestro.domain.models import Order, ProductionLine
from maestro.engines.planning.schemas import (
    PlanningData,
    PlanningRequest,
    PlanningResult,
    ValidationReport,
)


class PlanningStrategy(ABC):
    # ── 元信息 (供策略选择层使用) ──────────────────────────────
    name: str = ""
    applicable_product_lines: list[str] = []  # 适用的产品线
    scenario_description: str = ""  # 自然语言描述"何时该用它" (喂给 LLM 选择器)
    objective_type: str = ""  # 该策略优化的目标

    @abstractmethod
    def required_data(self) -> list[str]:
        """声明需要哪些额外数据 (如换型矩阵、模具数量、保质期)，供输入校验。"""

    @abstractmethod
    def validate_input(self, request: PlanningRequest, data: PlanningData) -> ValidationReport:
        """策略特有的输入完备性校验 (缺数据则报告)。"""

    @abstractmethod
    def solve(self, request: PlanningRequest, data: PlanningData) -> PlanningResult:
        """策略自己的建模+约束+算法。引擎不关心内部实现。"""

    @abstractmethod
    def explain_hints(self, result: PlanningResult) -> dict:
        """提供给 LLM 生成解释的结构化要点 (本策略关注什么、为何这么排)。"""


# ── 各策略共用的基础工具函数 ─────────────────────────────────


def usable_lines(request: PlanningRequest, data: PlanningData) -> list[ProductionLine]:
    """可用产线: 排除不可用与用户排除项；用户指定 line_ids 时只用指定项。"""
    lines = [l for l in data.lines if l.available and l.line_id not in request.excluded_lines]
    if request.line_ids:
        lines = [l for l in lines if l.line_id in request.line_ids]
    return lines


def eligible_lines(order: Order, lines: list[ProductionLine]) -> list[ProductionLine]:
    """订单可分配的产线 (产品匹配)。"""
    return [l for l in lines if order.product_id in l.supported_products]


def duration_days(order: Order, line: ProductionLine) -> int:
    """订单在某产线上的加工天数 = ceil(数量 / 日产能)。"""
    return max(1, math.ceil(order.quantity / line.capacity_per_day))


def basic_input_check(request: PlanningRequest, data: PlanningData) -> ValidationReport:
    """通用输入完备性校验: 有订单、有产线、每单有兼容产线。"""
    issues: list[str] = []
    if not data.orders:
        issues.append("没有可排产的订单")
    lines = usable_lines(request, data)
    if not lines:
        issues.append("没有可用产线")
    for o in data.orders:
        if lines and not eligible_lines(o, lines):
            issues.append(f"订单 {o.order_id} (产品 {o.product_id}) 没有兼容的可用产线")
    return ValidationReport(passed=not issues, issues=issues)
