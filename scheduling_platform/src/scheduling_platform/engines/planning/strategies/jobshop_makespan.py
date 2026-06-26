"""作业车间 — 最小完工时间策略 (OR-Tools CP-SAT)。

证明「同框架不同建模/目标」可共存: 与 FlowShopTardiness 同为 CP-SAT，
但目标改为最小化 makespan (全部订单最早整体完工)，适合注塑等设备受限、
追求设备周转的场景。

TODO(v0.2): 引入模具占用约束 (同一模具不可同时在两条线上)。
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


class JobShopMakespan(PlanningStrategy):
    name = "JobShopMakespan"
    applicable_product_lines = ["注塑"]
    scenario_description = (
        "作业车间排产，目标最小化整体完工时间(makespan)。"
        "适合注塑等设备(模具)受限、希望整批订单尽快全部完工、提高设备周转的场景。"
    )
    objective_type = "min_makespan"

    solver_time_limit_s: float = 10.0

    def required_data(self) -> list[str]:
        # TODO(v0.2): + 模具清单 (mold_inventory)
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
        makespan = model.NewIntVar(0, horizon, "makespan")

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
            model.Add(makespan >= end_o)
            order_vars[o.order_id] = {"options": options, "end": end_o}

        for ivs in line_intervals.values():
            if ivs:
                model.AddNoOverlap(ivs)
        model.Minimize(makespan)

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
            due_index = (o.due_date - data.today).days + 1
            assignments.append(
                Assignment(
                    order_id=oid,
                    product_id=o.product_id,
                    line_id=chosen["line"].line_id,
                    start_date=data.today + timedelta(days=start_day),
                    end_date=data.today + timedelta(days=end_day - 1),
                    due_date=o.due_date,
                    tardiness_days=max(0, end_day - due_index),
                )
            )
        assignments.sort(key=lambda a: (a.line_id, a.start_date))
        return PlanningResult(
            strategy_name=self.name,
            status="optimal" if status == cp_model.OPTIMAL else "feasible",
            assignments=assignments,
            objective_value=float(solver.ObjectiveValue()),
            kpis={
                "makespan_days": int(solver.Value(makespan)),
                "total_tardiness_days": sum(a.tardiness_days for a in assignments),
                "late_orders": [a.order_id for a in assignments if a.tardiness_days > 0],
            },
        )

    def explain_hints(self, result: PlanningResult) -> dict:
        return {
            "strategy_focus": "最小化整体完工时间(makespan): 让整批订单尽快全部下线，提高设备周转",
            "model": "作业车间模型，CP-SAT 精确求解；拖期是副产物指标而非优化目标",
            "makespan_days": result.kpis.get("makespan_days"),
            "late_orders": result.kpis.get("late_orders", []),
        }
