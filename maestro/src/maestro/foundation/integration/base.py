"""集成层抽象接口。

定义所有外部系统 (MES/ERP/WMS) 能力，业务层只依赖此接口，绝不直接写死外部系统调用。
替换 MockAdapter 为真实适配器时，引擎/workflow 代码无需改动。
"""

from abc import ABC, abstractmethod

from maestro.domain.models import (
    ActionResult,
    BomItem,
    Material,
    Order,
    ProductionLine,
    SystemEvent,
    WorkOrder,
)


class IntegrationAdapter(ABC):
    """外部系统统一抽象接口。"""

    # ── 读 (ERP/MES/WMS) ─────────────────────────────────────

    @abstractmethod
    async def get_orders(self, filters: dict | None = None) -> list[Order]:
        """查询订单。filters 支持: order_ids / status / product_id。"""

    @abstractmethod
    async def get_bom(self, product_id: str) -> list[BomItem]:
        """查询产品 BOM。"""

    @abstractmethod
    async def get_lines(self) -> list[ProductionLine]:
        """查询全部产线。"""

    @abstractmethod
    async def get_inventory(self, material_ids: list[str] | None = None) -> list[Material]:
        """查询库存。material_ids 为空时返回全部。"""

    @abstractmethod
    async def get_work_orders(self, filters: dict | None = None) -> list[WorkOrder]:
        """查询任务令。filters 支持: wo_ids / status / line_id。"""

    @abstractmethod
    async def get_material_status(self, material_id: str) -> dict:
        """物料状态归因: 卡在哪一环 (采购在途/质检/被占用) 及责任方/ETA。"""

    # ── 写 (必须经 AuthZ 后才可调用) ──────────────────────────

    @abstractmethod
    async def dispatch_work_order(self, wo_id: str) -> ActionResult:
        """下发任务令。"""

    @abstractmethod
    async def update_work_order_status(self, wo_id: str, status: str) -> ActionResult:
        """更新任务令状态。"""

    @abstractmethod
    async def send_message(self, recipient: str, channel: str, content: str) -> ActionResult:
        """发送消息 (催料/通知)。"""

    # ── 事件源 ───────────────────────────────────────────────

    @abstractmethod
    async def poll_events(self) -> list[SystemEvent]:
        """巡检拉取系统事件 (报警/异常等)。"""
