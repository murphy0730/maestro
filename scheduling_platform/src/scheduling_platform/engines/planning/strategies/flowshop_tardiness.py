"""流水车间 — 最小总拖期策略 (OR-Tools CP-SAT)。默认兜底策略。

最小可行车间模型: 决策每单分到哪条线及起止时间。
硬约束: 产线日产能(体现在加工天数)、产品匹配、排除不可用产线、同线不重叠。
目标: 最小化总拖期。无解时返回明确不可行原因。
"""

from datetime import timedelta

from ortools.sat.python import cp_model

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


class FlowShopTardiness(PlanningStrategy):
    name = "FlowShopTardiness"
    applicable_product_lines = ["*"]
    scenario_description = (
        "通用流水车间排产，目标最小化总拖期(尽量不延误交期)。"
        "适合交期敏感、无特殊工艺约束的大多数离散制造场景，是默认兜底策略。"
    )
    objective_type = "min_total_tardiness"

    solver_time_limit_s: float = 10.0

    def required_data(self) -> list[str]:
        return ["orders", "lines"]

    def validate_input(self, request: PlanningRequest, data: PlanningData) -> ValidationReport:
        return basic_input_check(request, data)

    def solve(self, request: PlanningRequest, data: PlanningData) -> PlanningResult:
        lines = usable_lines(request, data)
        for o in data.orders:
            if not eligible_lines(o, lines):
                return PlanningResult(
                    strategy_name=self.name,
                    status="infeasible",
                    infeasible_reason=f"订单 {o.order_id} (产品 {o.product_id}) 没有兼容的可用产线",
                )
        if not data.orders or not lines:
            return PlanningResult(
                strategy_name=self.name, status="infeasible",
                infeasible_reason="订单或可用产线为空",
            )

        model = cp_model.CpModel()
        horizon = sum(
            max(duration_days(o, l) for l in eligible_lines(o, lines)) for o in data.orders
        ) + 1
        line_intervals: dict[str, list] = {l.line_id: [] for l in lines}
        order_vars: dict[str, dict] = {}
        tardiness_vars = []

        for o in data.orders:
            options = []
            presences = []
            end_o = model.NewIntVar(0, horizon, f"end_{o.order_id}")
            for l in eligible_lines(o, lines):
                p = model.NewBoolVar(f"x_{o.order_id}_{l.line_id}")
                dur = duration_days(o, l)
                start = model.NewIntVar(0, horizon, f"s_{o.order_id}_{l.line_id}")
                end = model.NewIntVar(0, horizon, f"e_{o.order_id}_{l.line_id}")
                interval = model.NewOptionalIntervalVar(
                    start, dur, end, p, f"iv_{o.order_id}_{l.line_id}"
                )
                line_intervals[l.line_id].append(interval)
                model.Add(end_o == end).OnlyEnforceIf(p)
                options.append({"presence": p, "line": l, "start": start, "end": end})
                presences.append(p)
            model.AddExactlyOne(presences)
            # 完工日索引 ≤ due_day_index+1 视为不拖期 (end 为排他右边界)
            due_index = (o.due_date - data.today).days + 1
            # 上界须覆盖已过期订单 (due_index<0 时最大拖期 = horizon - due_index)，
            # 否则过期订单会让模型整体 infeasible 而非产出大拖期解
            tard = model.NewIntVar(0, max(horizon * 2, horizon - due_index), f"tard_{o.order_id}")
            model.Add(tard >= end_o - due_index)
            tardiness_vars.append(tard)
            order_vars[o.order_id] = {"options": options, "end": end_o, "tard": tard}

        for ivs in line_intervals.values():
            if ivs:
                model.AddNoOverlap(ivs)
        model.Minimize(sum(tardiness_vars))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.solver_time_limit_s
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return PlanningResult(
                strategy_name=self.name, status="infeasible",
                infeasible_reason="求解器在约束下未找到可行解 (产能/产品匹配冲突)",
            )

        assignments = []
        order_map = {o.order_id: o for o in data.orders}
        for oid, vars_ in order_vars.items():
            o = order_map[oid]
            chosen = next(opt for opt in vars_["options"] if solver.BooleanValue(opt["presence"]))
            start_day = solver.Value(chosen["start"])
            end_day = solver.Value(chosen["end"])
            assignments.append(
                Assignment(
                    order_id=oid,
                    product_id=o.product_id,
                    line_id=chosen["line"].line_id,
                    start_date=data.today + timedelta(days=start_day),
                    end_date=data.today + timedelta(days=end_day - 1),
                    due_date=o.due_date,
                    tardiness_days=solver.Value(vars_["tard"]),
                )
            )
        assignments.sort(key=lambda a: (a.line_id, a.start_date))
        total_tardiness = sum(a.tardiness_days for a in assignments)
        return PlanningResult(
            strategy_name=self.name,
            status="optimal" if status == cp_model.OPTIMAL else "feasible",
            assignments=assignments,
            objective_value=float(solver.ObjectiveValue()),
            kpis={
                "total_tardiness_days": total_tardiness,
                "late_orders": [a.order_id for a in assignments if a.tardiness_days > 0],
                "makespan_days": max((a.end_date - data.today).days + 1 for a in assignments),
            },
        )

    def explain_hints(self, result: PlanningResult) -> dict:
        return {
            "strategy_focus": "最小化总拖期: 优先保交期，紧急/早交期订单优先占用产能",
            "model": "流水车间模型，CP-SAT 精确求解，同一产线上订单顺序加工不重叠",
            "total_tardiness_days": result.kpis.get("total_tardiness_days"),
            "late_orders": result.kpis.get("late_orders", []),
        }
