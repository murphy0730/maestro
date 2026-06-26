"""任务令下发 workflow。

下发前前置校验 (齐套 OK + 产线可用 + 前道完成[初始版本桩]) → 满足才下发，
不满足则拦截并解释原因。下发是写操作 → 经 AuthZ (requires_confirmation)。
批量下发逐个校验，返回「待确认下发 / 被拦截(含原因)」两个清单。
"""

import logging

from scheduling_platform.engines.scheduling.schemas import DispatchOutcome
from scheduling_platform.engines.scheduling.workflows.kitting import KittingWorkflow
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate
from scheduling_platform.foundation.integration.base import IntegrationAdapter

logger = logging.getLogger(__name__)


class DispatchWorkflow:
    def __init__(
        self,
        adapter: IntegrationAdapter,
        gate: ActionGate,
        audit: AuditLog,
        kitting: KittingWorkflow,
    ):
        self._adapter = adapter
        self._gate = gate
        self._audit = audit
        self._kitting = kitting

    async def run(self, wo_ids: list[str] | None = None) -> DispatchOutcome:
        filters = {"wo_ids": wo_ids} if wo_ids else {"status": "draft"}
        work_orders = await self._adapter.get_work_orders(filters)
        lines = {l.line_id: l for l in await self._adapter.get_lines()}
        kitting_map = {
            r.wo_id: r for r in await self._kitting.check([w.wo_id for w in work_orders])
        } if work_orders else {}

        outcome = DispatchOutcome()
        for wo in work_orders:
            reasons: list[str] = []
            if wo.status != "draft":
                reasons.append(f"状态为 {wo.status}，仅 draft 可下发")
            kr = kitting_map.get(wo.wo_id)
            if kr and not kr.is_kitted:
                missing = ", ".join(
                    f"{s.material_id}缺{s.shortage_qty:g}{s.unit}" for s in kr.shortages
                )
                eta = f"，预计 {kr.estimated_ready_date} 齐套" if kr.estimated_ready_date else ""
                reasons.append(f"未齐套: {missing}{eta}")
            line = lines.get(wo.line_id)
            if line is None or not line.available:
                reasons.append(f"产线 {wo.line_id} 不可用")
            # TODO(v0.2): 前道工序完成校验 —— 初始版本视为已满足 (桩)
            if reasons:
                outcome.blocked.append({"wo_id": wo.wo_id, "reasons": reasons})
                self._audit.record(
                    actor="system",
                    action="dispatch_blocked",
                    params={"wo_id": wo.wo_id},
                    result={"reasons": reasons},
                )
                continue
            gate_result = await self._gate.request(
                "dispatch_work_order",
                description=f"下发任务令 {wo.wo_id} 到产线 {wo.line_id}",
                params={"wo_id": wo.wo_id, "line_id": wo.line_id},
                executor=lambda wid=wo.wo_id: self._adapter.dispatch_work_order(wid),
            )
            if gate_result.action:
                outcome.pending_actions.append(gate_result.action)
        return outcome
