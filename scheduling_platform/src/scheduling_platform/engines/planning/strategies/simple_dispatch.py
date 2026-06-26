"""纯派单规则策略 (EDD 最早交期优先，不调求解器)。

证明「非优化类算法也能作为策略插入」: 与 OR-Tools 策略实现同一接口、
平等共存，引擎完全不感知内部差异。
"""

from datetime import timedelta

from scheduling_platform.engines.planning.schemas import (
    Assignment,
    PlanningData,
    PlanningRequest,
    PlanningResult,
    ValidationReport,
)
from scheduling_platform.engines.planning.strategies.base import (
    PlanningStrategy,
    basic_input_check,
    duration_days,
    eligible_lines,
    usable_lines,
)


class SimpleDispatch(PlanningStrategy):
    name = "SimpleDispatch"
    applicable_product_lines = ["SMT贴片"]
    scenario_description = (
        "快速派单规则(EDD 最早交期优先)，不做优化求解，毫秒级出计划。"
        "适合规则即可满足的产线、或需要应急快速给出可执行计划的场景。"
    )
    objective_type = "edd_dispatch_rule"

    def required_data(self) -> list[str]:
        return ["orders", "lines"]

    def validate_input(self, request: PlanningRequest, data: PlanningData) -> ValidationReport:
        return basic_input_check(request, data)

    def solve(self, request: PlanningRequest, data: PlanningData) -> PlanningResult:
        lines = usable_lines(request, data)
        # EDD: 按交期升序，其次优先级
        pending = sorted(data.orders, key=lambda o: (o.due_date, o.priority))
        line_free: dict[str, int] = {l.line_id: 0 for l in lines}  # 每线下一空闲日索引
        assignments: list[Assignment] = []

        for o in pending:
            candidates = eligible_lines(o, lines)
            if not candidates:
                return PlanningResult(
                    strategy_name=self.name,
                    status="infeasible",
                    infeasible_reason=f"订单 {o.order_id} (产品 {o.product_id}) 没有兼容的可用产线",
                )
            # 贪心: 选最早完工的产线
            best = min(candidates, key=lambda l: line_free[l.line_id] + duration_days(o, l))
            start = line_free[best.line_id]
            dur = duration_days(o, best)
            end = start + dur
            line_free[best.line_id] = end
            due_index = (o.due_date - data.today).days + 1
            assignments.append(
                Assignment(
                    order_id=o.order_id,
                    product_id=o.product_id,
                    line_id=best.line_id,
                    start_date=data.today + timedelta(days=start),
                    end_date=data.today + timedelta(days=end - 1),
                    due_date=o.due_date,
                    tardiness_days=max(0, end - due_index),
                )
            )

        return PlanningResult(
            strategy_name=self.name,
            status="feasible",  # 规则解不保证最优
            assignments=assignments,
            objective_value=None,
            kpis={
                "rule": "EDD 最早交期优先 + 最早完工产线贪心",
                "total_tardiness_days": sum(a.tardiness_days for a in assignments),
                "late_orders": [a.order_id for a in assignments if a.tardiness_days > 0],
            },
        )

    def explain_hints(self, result: PlanningResult) -> dict:
        return {
            "strategy_focus": "EDD 派单规则: 交期最早的订单最先排，贪心选最早能完工的产线",
            "model": "无优化求解器，规则直接生成，结果可执行但不保证最优",
            "late_orders": result.kpis.get("late_orders", []),
        }


# TODO(v0.2): 其余真实产品线策略，照 PlanningStrategy 基类补即可:
#   - SetupMinimizeHeuristic: SMT 换型最少 (元启发式)
#   - BatchProcessScheduling: 流程批量 + 保质期约束 (食品灌装)
