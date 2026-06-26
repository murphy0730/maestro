"""内置工具 — 全部通过 IntegrationAdapter 实现，写操作经 ActionGate(AuthZ)。"""

from typing import TYPE_CHECKING

from scheduling_platform.foundation.authz import ActionGate, gate_outcome_summary
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from scheduling_platform.engines.scheduling.workflows.kitting import KittingWorkflow


def register_builtin_tools(
    registry: ToolRegistry,
    adapter: IntegrationAdapter,
    gate: ActionGate,
    kitting: "KittingWorkflow",
) -> None:
    """注册内置工具。run_scheduling_solver 由排产引擎对话入口承载，
    不在工具层重复暴露 (TODO(v0.2): 供复合任务编排调用)。"""

    async def query_orders(order_ids: list[str] | None = None, status: str | None = None):
        filters: dict = {}
        if order_ids:
            filters["order_ids"] = order_ids
        if status:
            filters["status"] = status
        return [o.model_dump(mode="json") for o in await adapter.get_orders(filters)]

    async def query_inventory(material_ids: list[str] | None = None):
        return [m.model_dump(mode="json") for m in await adapter.get_inventory(material_ids)]

    async def query_work_orders(wo_ids: list[str] | None = None, status: str | None = None):
        filters: dict = {}
        if wo_ids:
            filters["wo_ids"] = wo_ids
        if status:
            filters["status"] = status
        return [w.model_dump(mode="json") for w in await adapter.get_work_orders(filters)]

    async def check_kitting(wo_ids: list[str] | None = None):
        results = await kitting.check(wo_ids)
        return [r.model_dump(mode="json") for r in results]

    async def analyze_material_shortage(material_id: str):
        return await adapter.get_material_status(material_id)

    async def send_expedite_message(
        recipient: str, content: str, recipient_type: str = "internal", channel: str = "im"
    ):
        action_type = f"send_expedite_message.{'supplier' if recipient_type == 'supplier' else 'internal'}"
        outcome = await gate.request(
            action_type,
            description=f"向 {recipient} 发送催料消息",
            params={"recipient": recipient, "channel": channel, "content": content},
            executor=lambda: adapter.send_message(recipient, channel, content),
        )
        return {"status": outcome.status, "summary": gate_outcome_summary(outcome)}

    async def dispatch_work_order(wo_id: str):
        outcome = await gate.request(
            "dispatch_work_order",
            description=f"下发任务令 {wo_id}",
            params={"wo_id": wo_id},
            executor=lambda: adapter.dispatch_work_order(wo_id),
        )
        return {"status": outcome.status, "summary": gate_outcome_summary(outcome)}

    _str_list = {"type": "array", "items": {"type": "string"}}
    registry.register(
        "query_orders",
        "查询生产订单 (可按订单号列表或状态过滤)",
        {
            "type": "object",
            "properties": {"order_ids": _str_list, "status": {"type": "string"}},
        },
        query_orders,
    )
    registry.register(
        "query_inventory",
        "查询物料库存 (可按物料号列表过滤，留空返回全部)",
        {"type": "object", "properties": {"material_ids": _str_list}},
        query_inventory,
    )
    registry.register(
        "query_work_orders",
        "查询任务令 (可按任务令号或状态过滤)",
        {
            "type": "object",
            "properties": {"wo_ids": _str_list, "status": {"type": "string"}},
        },
        query_work_orders,
    )
    registry.register(
        "check_kitting",
        "对任务令做齐套检查，返回缺料清单与预计齐套时间 (wo_ids 留空检查全部待开工)",
        {"type": "object", "properties": {"wo_ids": _str_list}},
        check_kitting,
    )
    registry.register(
        "analyze_material_shortage",
        "缺料归因: 判断某物料卡在哪一环 (采购在途/质检/被占用) 及责任方",
        {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
        },
        analyze_material_shortage,
    )
    registry.register(
        "send_expedite_message",
        "发送催料消息 (写操作，经权限分级: 内部自动发，供应商需人确认)",
        {
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "content": {"type": "string"},
                "recipient_type": {"type": "string", "enum": ["internal", "supplier"]},
                "channel": {"type": "string"},
            },
            "required": ["recipient", "content"],
        },
        send_expedite_message,
    )
    registry.register(
        "dispatch_work_order",
        "下发任务令到产线 (写操作，需人确认)",
        {
            "type": "object",
            "properties": {"wo_id": {"type": "string"}},
            "required": ["wo_id"],
        },
        dispatch_work_order,
    )
