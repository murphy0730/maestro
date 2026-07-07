"""齐套检查服务 (共享底座)。

对每个任务令: 订单 → BOM → 比对库存/在途 → 算缺口 → KittingResult。
纯查询+计算，无写操作。v0.1 由调度引擎的 workflow 持有；v0.2 中调度引擎改为
ReAct 智能体，齐套成为被多方 (check_kitting 工具 / 巡检 / 下发前置断言) 复用的
底座能力，故上移到 foundation。

TODO(v0.2): 多任务令共用物料时做库存分配 (当前各自独立比对在库量)。
"""

import logging
from datetime import date

from maestro.domain.models import KittingResult, Shortage
from maestro.foundation.audit import AuditLog
from maestro.foundation.integration.base import IntegrationAdapter

logger = logging.getLogger(__name__)


class KittingService:
    def __init__(self, adapter: IntegrationAdapter, audit: AuditLog):
        self._adapter = adapter
        self._audit = audit

    async def check(self, wo_ids: list[str] | None = None) -> list[KittingResult]:
        """齐套检查。wo_ids 为空时检查全部待开工 (draft/blocked) 任务令。"""
        filters = {"wo_ids": wo_ids} if wo_ids else {"status": ["draft", "blocked"]}
        work_orders = await self._adapter.get_work_orders(filters)
        inventory = {m.material_id: m for m in await self._adapter.get_inventory()}

        results: list[KittingResult] = []
        for wo in work_orders:
            orders = await self._adapter.get_orders({"order_ids": [wo.order_id]})
            if not orders:
                logger.warning("[KITTING] 任务令 %s 对应订单 %s 不存在", wo.wo_id, wo.order_id)
                continue
            order = orders[0]
            bom = await self._adapter.get_bom(order.product_id)

            shortages: list[Shortage] = []
            etas: list[date] = []
            all_covered_by_transit = True
            for item in bom:
                required = item.qty_per_unit * order.quantity
                mat = inventory.get(item.material_id)
                on_hand = mat.on_hand_qty if mat else 0.0
                if on_hand >= required:
                    continue
                gap = required - on_hand
                shortages.append(
                    Shortage(
                        material_id=item.material_id,
                        material_name=item.material_name or (mat.name if mat else ""),
                        required_qty=required,
                        available_qty=on_hand,
                        shortage_qty=gap,
                        unit=mat.unit if mat else "pcs",
                    )
                )
                in_transit = mat.in_transit_qty if mat else 0.0
                status = await self._adapter.get_material_status(item.material_id)
                eta_str = status.get("eta")
                if in_transit >= gap and eta_str:
                    etas.append(date.fromisoformat(eta_str))
                else:
                    all_covered_by_transit = False

            results.append(
                KittingResult(
                    wo_id=wo.wo_id,
                    is_kitted=not shortages,
                    shortages=shortages,
                    estimated_ready_date=(
                        max(etas) if shortages and etas and all_covered_by_transit else None
                    ),
                )
            )

        self._audit.record(
            actor="system",
            action="kitting_check",
            params={"wo_ids": wo_ids or "all_pending"},
            result={
                "checked": len(results),
                "not_kitted": [r.wo_id for r in results if not r.is_kitted],
            },
        )
        return results
