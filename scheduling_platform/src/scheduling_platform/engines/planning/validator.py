"""通用硬约束校验 — 独立于策略，不信任求解器、二次确认。

策略特有约束 (换型可行性、保质期、模具占用) 由各策略 validate_input /
结果自检负责，不在此层。
"""

from scheduling_platform.engines.planning.schemas import (
    PlanningData,
    PlanningRequest,
    PlanningResult,
    ValidationReport,
)
from scheduling_platform.engines.planning.strategies.base import duration_days


class PlanValidator:
    def validate(
        self, result: PlanningResult, request: PlanningRequest, data: PlanningData
    ) -> ValidationReport:
        issues: list[str] = []
        line_map = {l.line_id: l for l in data.lines}
        order_map = {o.order_id: o for o in data.orders}

        for a in result.assignments:
            line = line_map.get(a.line_id)
            order = order_map.get(a.order_id)
            if line is None:
                issues.append(f"{a.order_id}: 产线 {a.line_id} 不存在")
                continue
            if order is None:
                issues.append(f"分配中出现未知订单 {a.order_id}")
                continue
            if not line.available:
                issues.append(f"{a.order_id}: 产线 {a.line_id} 不可用")
            if a.line_id in request.excluded_lines:
                issues.append(f"{a.order_id}: 产线 {a.line_id} 已被用户排除")
            if order.product_id not in line.supported_products:
                issues.append(f"{a.order_id}: 产线 {a.line_id} 不支持产品 {order.product_id}")
            # 产能: 占用天数必须 ≥ ceil(数量/日产能)
            span = (a.end_date - a.start_date).days + 1
            need = duration_days(order, line)
            if span < need:
                issues.append(
                    f"{a.order_id}: 在 {a.line_id} 仅排 {span} 天，按日产能需 {need} 天，产能超限"
                )

        # 同一产线时间窗不重叠
        by_line: dict[str, list] = {}
        for a in result.assignments:
            by_line.setdefault(a.line_id, []).append(a)
        for line_id, items in by_line.items():
            items.sort(key=lambda a: a.start_date)
            for prev, cur in zip(items, items[1:]):
                if cur.start_date <= prev.end_date:
                    issues.append(
                        f"产线 {line_id}: {prev.order_id} 与 {cur.order_id} 时间窗重叠"
                    )

        late = [a for a in result.assignments if a.tardiness_days > 0]
        stats = {
            "orders_planned": len(result.assignments),
            "lines_used": sorted(by_line.keys()),
            "total_tardiness_days": sum(a.tardiness_days for a in late),
            "late_orders": {a.order_id: a.tardiness_days for a in late},
        }
        return ValidationReport(passed=not issues, issues=issues, stats=stats)
