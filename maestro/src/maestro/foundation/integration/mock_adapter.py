"""模拟 MES/ERP/WMS 适配器。

读接口从 data/mock/*.json 加载数据；写接口打印日志并记录到内存 outbox /
action_log，不真正调用外部系统；poll_events 按预置规则产生模拟事件。
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from maestro.domain.models import (
    ActionResult,
    BomItem,
    Material,
    Order,
    ProductionLine,
    SystemEvent,
    WorkOrder,
)
from maestro.foundation.integration.base import IntegrationAdapter

logger = logging.getLogger(__name__)

# 物料状态归因预置表: stage ∈ purchasing_in_transit / quality_inspection / occupied
_MATERIAL_STATUS: dict[str, dict] = {
    "M-002": {
        "stage": "purchasing_in_transit",
        "supplier": "苏州精工五金",
        "buyer": "采购-王伟",
        "eta": "2026-06-13",
        "detail": "采购单 PO-8821 在途，预计 06-13 到货",
    },
    "M-003": {
        "stage": "quality_inspection",
        "owner": "质检-李娜",
        "detail": "批次 B-0607 到货后待检 2 天，卡在 IQC",
    },
    "M-005": {
        "stage": "purchasing_in_transit",
        "supplier": "深圳芯源电子",
        "buyer": "采购-陈晨",
        "eta": "2026-06-14",
        "detail": "采购单 PO-8830 在途，预计 06-14 到货",
    },
}


class MockAdapter(IntegrationAdapter):
    """Mock 实现。后续替换为真实适配器时业务代码不变。"""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._orders = [Order(**x) for x in self._load("orders.json")]
        self._bom = [BomItem(**x) for x in self._load("bom.json")]
        self._lines = [ProductionLine(**x) for x in self._load("lines.json")]
        self._inventory = [Material(**x) for x in self._load("inventory.json")]
        self._work_orders = [WorkOrder(**x) for x in self._load("work_orders.json")]

        self.outbox: list[dict] = []  # 模拟消息出口 (不真发)
        self.action_log: list[dict] = []  # 模拟写操作记录
        # 预置事件: 首次巡检时拉到一条设备报警，演示事件驱动链路
        self._pending_events: list[SystemEvent] = [
            SystemEvent(
                type="equipment_alarm",
                payload={
                    "line_id": "L2",
                    "description": "注塑2号线 锁模压力异常报警",
                    "affected_wo_ids": ["WO-102"],
                },
            )
        ]

    def _load(self, filename: str) -> list[dict]:
        path = self._data_dir / filename
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 读 ──────────────────────────────────────────────────

    async def get_orders(self, filters: dict | None = None) -> list[Order]:
        filters = filters or {}
        result = self._orders
        if ids := filters.get("order_ids"):
            result = [o for o in result if o.order_id in ids]
        if status := filters.get("status"):
            statuses = [status] if isinstance(status, str) else status
            result = [o for o in result if o.status in statuses]
        if product_id := filters.get("product_id"):
            result = [o for o in result if o.product_id == product_id]
        return list(result)

    async def get_bom(self, product_id: str) -> list[BomItem]:
        return [b for b in self._bom if b.product_id == product_id]

    async def get_lines(self) -> list[ProductionLine]:
        return list(self._lines)

    async def get_inventory(self, material_ids: list[str] | None = None) -> list[Material]:
        if not material_ids:
            return list(self._inventory)
        return [m for m in self._inventory if m.material_id in material_ids]

    async def get_work_orders(self, filters: dict | None = None) -> list[WorkOrder]:
        filters = filters or {}
        result = self._work_orders
        if ids := filters.get("wo_ids"):
            result = [w for w in result if w.wo_id in ids]
        if status := filters.get("status"):
            statuses = [status] if isinstance(status, str) else status
            result = [w for w in result if w.status in statuses]
        if line_id := filters.get("line_id"):
            result = [w for w in result if w.line_id == line_id]
        return list(result)

    async def get_material_status(self, material_id: str) -> dict:
        status = _MATERIAL_STATUS.get(
            material_id,
            {"stage": "occupied", "owner": "计划-张三", "detail": "库存被其它任务令占用"},
        )
        return {"material_id": material_id, **status}

    # ── 写 (调用方必须已经过 AuthZ) ───────────────────────────

    async def dispatch_work_order(self, wo_id: str) -> ActionResult:
        wo = next((w for w in self._work_orders if w.wo_id == wo_id), None)
        if wo is None:
            return ActionResult(success=False, action="dispatch_work_order", detail=f"任务令 {wo_id} 不存在")
        wo.status = "dispatched"
        self._record("dispatch_work_order", {"wo_id": wo_id})
        logger.info("[MOCK-MES] 任务令 %s 已下发", wo_id)
        return ActionResult(success=True, action="dispatch_work_order", detail=f"任务令 {wo_id} 已下发(模拟)", ref_id=wo_id)

    async def update_work_order_status(self, wo_id: str, status: str) -> ActionResult:
        wo = next((w for w in self._work_orders if w.wo_id == wo_id), None)
        if wo is None:
            return ActionResult(success=False, action="update_work_order_status", detail=f"任务令 {wo_id} 不存在")
        wo.status = status  # type: ignore[assignment]
        self._record("update_work_order_status", {"wo_id": wo_id, "status": status})
        logger.info("[MOCK-MES] 任务令 %s 状态 → %s", wo_id, status)
        return ActionResult(success=True, action="update_work_order_status", detail=f"{wo_id} → {status}", ref_id=wo_id)

    async def send_message(self, recipient: str, channel: str, content: str) -> ActionResult:
        msg = {
            "recipient": recipient,
            "channel": channel,
            "content": content,
            "sent_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.outbox.append(msg)
        self._record("send_message", msg)
        logger.info("[MOCK-OUTBOX] → %s (%s): %s", recipient, channel, content)
        return ActionResult(success=True, action="send_message", detail=f"已写入 outbox → {recipient}")

    def _record(self, action: str, params: dict) -> None:
        self.action_log.append({"action": action, "params": params, "at": datetime.now().isoformat(timespec="seconds")})

    # ── 事件源 ───────────────────────────────────────────────

    async def poll_events(self) -> list[SystemEvent]:
        """返回并清空预置事件 (一次性)，模拟从 MES 拉到报警。"""
        events, self._pending_events = self._pending_events, []
        return events
