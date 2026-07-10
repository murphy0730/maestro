"""内置工具 — 调度 ReAct 智能体与查询引擎的工具集。

全部通过 IntegrationAdapter 实现 (不直接写死外部系统)。工具分三类:
- read: 只读查询/分析，ReAct 自由调用。
- write: 有副作用的写操作，经 ActionGate(AuthZ) 授权；高危写操作另由组装根挂载
  前置断言 (preconditions.py)，构成「前置断言 + 授权」两道护栏。
- aux: 辅助 (LLM 分类 / 记录跟踪)。

写操作前的「前置断言」不在此注册 (避免 foundation 依赖引擎)，由 bootstrap 用
registry.attach_precondition 挂载。
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from maestro.domain.models import ActionResult
from maestro.foundation.authz import ActionGate, GateOutcome, gate_outcome_summary
from maestro.foundation.integration.base import IntegrationAdapter
from maestro.foundation.kitting import KittingService
from maestro.foundation.llm import LLMClient, LLMError
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ExceptionAssessment(BaseModel):
    """异常分类与定级 (classify_exception 工具的结构化输出)。"""

    type: Literal["equipment", "material", "quality", "personnel", "process"]
    severity: Literal["low", "medium", "high", "critical"]
    reason: str = ""


class FollowupStore:
    """跟踪/复盘记录 + 催料去重 (内存)。

    - record_followup 工具写入跟踪记录。
    - send_expedite_message 的前置断言用 `was_expedited` 防重复催。
    """

    def __init__(self):
        self.records: list[dict] = []
        self._expedited: set[str] = set()  # 已催物料 (防重复催)

    def add(self, note: str, wo_id: str | None = None, material_id: str | None = None) -> dict:
        rec = {
            "note": note,
            "wo_id": wo_id,
            "material_id": material_id,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        self.records.append(rec)
        return rec

    def mark_expedited(self, material_id: str) -> None:
        self._expedited.add(material_id)

    def was_expedited(self, material_id: str) -> bool:
        return material_id in self._expedited


def _gate_result(outcome: GateOutcome) -> dict:
    """写操作工具的统一返回: 状态 + 摘要 + (待确认时) action_id，供 ReAct 观察。"""
    result = {"status": outcome.status, "summary": gate_outcome_summary(outcome)}
    if outcome.action is not None:
        result["action_id"] = outcome.action.action_id
    return result


def _rule_assess(description: str) -> ExceptionAssessment:
    """LLM 不可用时的异常分类降级 (关键词规则)。"""
    if any(k in description for k in ("报警", "停机", "设备", "压力", "温度", "故障")):
        return ExceptionAssessment(type="equipment", severity="high", reason="关键词规则: 设备类")
    if any(k in description for k in ("缺料", "物料", "断料")):
        return ExceptionAssessment(type="material", severity="medium", reason="关键词规则: 物料类")
    if any(k in description for k in ("质量", "不良", "报废")):
        return ExceptionAssessment(type="quality", severity="high", reason="关键词规则: 质量类")
    if any(k in description for k in ("请假", "缺勤", "人员")):
        return ExceptionAssessment(type="personnel", severity="medium", reason="关键词规则: 人员类")
    return ExceptionAssessment(type="process", severity="medium", reason="关键词规则: 默认工艺类")


_ASSESS_SYSTEM = (
    "你是生产异常分诊员。把异常归类 (equipment/material/quality/personnel/process) "
    "并判定紧急度 (low/medium/high/critical)。依据: 是否停线、影响范围、交期威胁。"
)


def register_builtin_tools(
    registry: ToolRegistry,
    adapter: IntegrationAdapter,
    gate: ActionGate,
    kitting: KittingService,
    llm: LLMClient,
    followups: FollowupStore,
    observations: ObservationStore | None = None,
) -> None:
    # ── 只读类 (ReAct 自由调用) ──────────────────────────────

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

    async def analyze_exception_impact(wo_ids: list[str] | None = None):
        """异常影响分析: 受影响任务令 + 受威胁订单交期 (近 7 天)。"""
        wos = await adapter.get_work_orders({"wo_ids": wo_ids}) if wo_ids else []
        threatened = []
        if wos:
            orders = await adapter.get_orders({"order_ids": [w.order_id for w in wos]})
            deadline = date.today() + timedelta(days=7)
            threatened = [
                {"order_id": o.order_id, "due_date": o.due_date.isoformat()}
                for o in orders
                if o.due_date <= deadline
            ]
        return {
            "affected_work_orders": [w.wo_id for w in wos],
            "threatened_orders": threatened,
        }

    # ── 写操作类 (经 AuthZ；高危项另挂前置断言) ────────────────

    async def send_expedite_message(
        recipient: str,
        content: str,
        recipient_type: str = "internal",
        channel: str = "im",
        material_id: str | None = None,
    ):
        action_type = (
            "send_expedite_message.supplier"
            if recipient_type == "supplier"
            else "send_expedite_message.internal"
        )
        outcome = await gate.request(
            action_type,
            description=f"向 {recipient} 发送催料消息",
            params={
                "recipient": recipient,
                "channel": channel,
                "content": content,
                "material_id": material_id,
            },
            executor=lambda: adapter.send_message(recipient, channel, content),
        )
        if material_id and outcome.status in ("executed", "pending"):
            followups.mark_expedited(material_id)
        return _gate_result(outcome)

    async def dispatch_work_order(wo_id: str):
        outcome = await gate.request(
            "dispatch_work_order",
            description=f"下发任务令 {wo_id}",
            params={"wo_id": wo_id},
            executor=lambda: adapter.dispatch_work_order(wo_id),
        )
        return _gate_result(outcome)

    async def update_work_order_status(wo_id: str, status: str):
        outcome = await gate.request(
            "update_work_order_status",
            description=f"更新任务令 {wo_id} 状态为 {status}",
            params={"wo_id": wo_id, "status": status},
            executor=lambda: adapter.update_work_order_status(wo_id, status),
        )
        return _gate_result(outcome)

    async def notify_personnel(recipient: str, content: str, channel: str = "im"):
        outcome = await gate.request(
            "send_notification",
            description=f"通知 {recipient}",
            params={"recipient": recipient, "channel": channel, "content": content},
            executor=lambda: adapter.send_message(recipient, channel, content),
        )
        return _gate_result(outcome)

    # ── 辅助类 ───────────────────────────────────────────────

    async def classify_exception(description: str):
        try:
            assessment = await llm.classify(_ASSESS_SYSTEM, description, ExceptionAssessment)
        except LLMError:
            assessment = _rule_assess(description)
        return assessment.model_dump()

    async def record_followup(note: str, wo_id: str | None = None, material_id: str | None = None):
        async def _execute() -> ActionResult:
            rec = followups.add(note, wo_id, material_id)
            return ActionResult(
                success=True,
                action="record_followup",
                detail=json.dumps(rec, ensure_ascii=False, default=str),
            )

        outcome = await gate.request(
            "record_followup",
            description=f"记录跟踪: {note}",
            params={"note": note, "wo_id": wo_id, "material_id": material_id},
            executor=_execute,
        )
        return _gate_result(outcome)

    async def read_observation(
        ref: str, offset: int = 0, limit: int = 20, keys: list[str] | None = None
    ):
        """分页取回一个被离线暂存的大观察 (observation_ref)。"""
        if observations is None:
            return {"error": "观察暂存不可用 (未配置 ObservationStore)"}
        return observations.get(ref, offset=offset, limit=limit, keys=keys)

    # ── 注册 (含 JSON schema 与 kind) ─────────────────────────

    _str_list = {"type": "array", "items": {"type": "string"}}
    registry.register(
        "query_orders",
        "查询生产订单 (可按订单号列表或状态过滤)",
        {"type": "object", "properties": {"order_ids": _str_list, "status": {"type": "string"}}},
        query_orders,
        kind="read",
    )
    registry.register(
        "query_inventory",
        "查询物料库存 (可按物料号列表过滤，留空返回全部)",
        {"type": "object", "properties": {"material_ids": _str_list}},
        query_inventory,
        kind="read",
    )
    registry.register(
        "query_work_orders",
        "查询任务令 (可按任务令号或状态过滤)",
        {"type": "object", "properties": {"wo_ids": _str_list, "status": {"type": "string"}}},
        query_work_orders,
        kind="read",
    )
    registry.register(
        "check_kitting",
        "对任务令做齐套检查，返回缺料清单与预计齐套时间 (wo_ids 留空检查全部待开工)",
        {"type": "object", "properties": {"wo_ids": _str_list}},
        check_kitting,
        kind="read",
    )
    registry.register(
        "analyze_material_shortage",
        "缺料归因: 判断某物料卡在哪一环 (采购在途/质检/被占用) 及责任方/ETA",
        {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
        },
        analyze_material_shortage,
        kind="read",
    )
    registry.register(
        "analyze_exception_impact",
        "异常影响分析: 给定受影响任务令，返回受影响任务令与受威胁交期订单",
        {"type": "object", "properties": {"wo_ids": _str_list}},
        analyze_exception_impact,
        kind="read",
    )
    registry.register(
        "send_expedite_message",
        "发送催料消息 (写操作)。internal 自动发，supplier 需人确认。"
        "建议带 material_id 以便前置断言核实确实缺料且防重复催。",
        {
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "content": {"type": "string"},
                "recipient_type": {"type": "string", "enum": ["internal", "supplier"]},
                "channel": {"type": "string"},
                "material_id": {"type": "string"},
            },
            "required": ["recipient", "content"],
        },
        send_expedite_message,
        kind="write",
    )
    registry.register(
        "dispatch_work_order",
        "下发任务令到产线 (写操作，需人确认；前置断言要求已齐套且产线可用)",
        {"type": "object", "properties": {"wo_id": {"type": "string"}}, "required": ["wo_id"]},
        dispatch_work_order,
        kind="write",
    )
    registry.register(
        "update_work_order_status",
        "更新任务令状态 (写操作，需人确认)",
        {
            "type": "object",
            "properties": {"wo_id": {"type": "string"}, "status": {"type": "string"}},
            "required": ["wo_id", "status"],
        },
        update_work_order_status,
        kind="write",
    )
    registry.register(
        "notify_personnel",
        "通知相关人员到场/处置 (写操作，需人确认)",
        {
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "content": {"type": "string"},
                "channel": {"type": "string"},
            },
            "required": ["recipient", "content"],
        },
        notify_personnel,
        kind="write",
    )
    registry.register(
        "classify_exception",
        "异常分类定级: 输入异常描述，返回类型与紧急度 (LLM，失败降级关键词规则)",
        {
            "type": "object",
            "properties": {"description": {"type": "string"}},
            "required": ["description"],
        },
        classify_exception,
        kind="aux",
    )
    registry.register(
        "record_followup",
        "记录跟踪/复盘 (催料、异常处置的后续待办)",
        {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "wo_id": {"type": "string"},
                "material_id": {"type": "string"},
            },
            "required": ["note"],
        },
        record_followup,
        kind="write",
    )
    registry.register(
        "read_observation",
        "分页取回被离线暂存的大工具结果 (当某次工具观察过大返回 observation_ref 时使用)。"
        "list 用 offset/limit 翻页；dict 可传 keys 取子集；不要臆造未取回的内容。",
        {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "keys": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["ref"],
        },
        read_observation,
        kind="read",
    )


def scheduling_tools(registry: ToolRegistry) -> list[str]:
    """scheduling 引擎可调度的工具白名单 = 注册表全集 (read + write + aux)。

    动态派生而非手写列表: 新增内置工具只要注册进 registry 就自动可被调度引擎调用，
    不必再改这里。调用点须在所有工具注册完成之后 (见 bootstrap.build_platform)。

    放开「能否被调用」不等于放开「能否直接执行」—— 写操作仍逐一经 ActionGate 判级,
    写生产系统的动作无论何种执行模式都需人工确认 (foundation/permissions.py)。
    """
    return registry.names()

# 查询引擎可用的只读工具 (绝不含写操作)
QUERY_READONLY_TOOLS = [
    "query_orders",
    "query_inventory",
    "query_work_orders",
    "check_kitting",
    "read_observation",
]
