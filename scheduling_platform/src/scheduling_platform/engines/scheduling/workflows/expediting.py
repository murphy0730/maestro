"""催料闭环 workflow。

缺料归因 → 确定催料对象(规则表驱动) → LLM 生成措辞得体的文案 →
AuthZ 分级发送 (内部 auto 写 outbox / 供应商 requires_confirmation 待确认) →
记录已催记录。

TODO(v0.2): 闭环跟踪 —— 超时未回应自动升级 (此处仅记录，钩子已留)。
"""

import json
import logging

from scheduling_platform.domain.models import KittingResult, Shortage
from scheduling_platform.engines.scheduling.schemas import (
    ExpediteMessage,
    ExpediteRecord,
    ExpeditingOutcome,
)
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

# 归因 → (催料对象类型, 收件人字段优先级, 意图说明) 规则表
TARGET_RULES: dict[str, tuple[str, list[str], str]] = {
    "purchasing_in_transit": ("supplier", ["supplier", "buyer"], "向供应商催交在途物料"),
    "quality_inspection": ("internal", ["owner"], "催质检加急检验放行"),
    "occupied": ("internal", ["owner"], "请计划员协调释放被占用物料"),
}

COMPOSE_SYSTEM = """你是制造企业的催料文案助手。根据缺料上下文生成一条催料消息。
要求措辞得体: 对供应商礼貌专业、说明影响与期望交期；对内部同事直接清晰、说明优先级。
recipient 必须用上下文中给出的收件人。content 为完整可直接发送的中文消息。"""


class ExpeditingWorkflow:
    def __init__(
        self,
        adapter: IntegrationAdapter,
        gate: ActionGate,
        audit: AuditLog,
        llm: LLMClient,
    ):
        self._adapter = adapter
        self._gate = gate
        self._audit = audit
        self._llm = llm
        self.records: list[ExpediteRecord] = []  # 已催记录 (闭环跟踪骨架)

    async def run(self, kitting_results: list[KittingResult]) -> ExpeditingOutcome:
        outcome = ExpeditingOutcome()
        expedited: set[tuple[str, str]] = set()  # (material_id, recipient) 去重

        for kr in kitting_results:
            if kr.is_kitted:
                continue
            for shortage in kr.shortages:
                # 1) 缺料归因
                status = await self._adapter.get_material_status(shortage.material_id)
                stage = status.get("stage", "occupied")
                # 2) 确定催料对象 (规则表驱动)
                target_type, recipient_fields, intent = TARGET_RULES.get(
                    stage, TARGET_RULES["occupied"]
                )
                recipient = next(
                    (status[f] for f in recipient_fields if status.get(f)), "采购部"
                )
                if (shortage.material_id, recipient) in expedited:
                    continue
                expedited.add((shortage.material_id, recipient))
                # 3) 生成催料文案 (LLM, 失败降级模板)
                content = await self._compose(shortage, kr.wo_id, status, target_type, recipient, intent)
                # 4) 授权与发送
                action_type = f"send_expedite_message.{target_type}"
                gate_result = await self._gate.request(
                    action_type,
                    description=f"向 {recipient} 催料 {shortage.material_id}({shortage.material_name})",
                    params={
                        "material_id": shortage.material_id,
                        "wo_id": kr.wo_id,
                        "recipient": recipient,
                        "stage": stage,
                        "content": content,
                    },
                    executor=lambda r=recipient, c=content: self._adapter.send_message(r, "im", c),
                )
                record = ExpediteRecord(
                    material_id=shortage.material_id,
                    material_name=shortage.material_name,
                    wo_id=kr.wo_id,
                    stage=stage,
                    target_type=target_type,  # type: ignore[arg-type]
                    recipient=recipient,
                    content=content,
                    status={
                        "executed": "sent",
                        "pending": "pending_confirmation",
                        "denied": "denied",
                    }[gate_result.status],
                    action_id=gate_result.action.action_id if gate_result.action else None,
                )
                # 5) 闭环跟踪 (骨架): 仅记录。TODO(v0.2): 超时未回应自动升级
                self.records.append(record)
                outcome.records.append(record)
                if gate_result.action:
                    outcome.pending_actions.append(gate_result.action)

        return outcome

    async def _compose(
        self,
        shortage: Shortage,
        wo_id: str,
        status: dict,
        target_type: str,
        recipient: str,
        intent: str,
    ) -> str:
        context = {
            "intent": intent,
            "target_type": target_type,
            "recipient": recipient,
            "material": shortage.model_dump(),
            "wo_id": wo_id,
            "attribution": status,
        }
        try:
            msg = await self._llm.classify(
                COMPOSE_SYSTEM, json.dumps(context, ensure_ascii=False), ExpediteMessage
            )
            return msg.content
        except LLMError:
            return self._template(shortage, wo_id, status, target_type, recipient)

    @staticmethod
    def _template(
        shortage: Shortage, wo_id: str, status: dict, target_type: str, recipient: str
    ) -> str:
        mat = f"{shortage.material_name}({shortage.material_id})"
        gap = f"{shortage.shortage_qty:g}{shortage.unit}"
        if target_type == "supplier":
            eta = status.get("eta", "未知")
            return (
                f"{recipient} 您好：我司生产任务令 {wo_id} 因物料 {mat} 缺口 {gap} 面临停工，"
                f"系统显示在途预计 {eta} 到货。烦请确认能否提前交付或告知准确到货时间，谢谢配合。"
            )
        if status.get("stage") == "quality_inspection":
            return (
                f"{recipient}：物料 {mat} 当前卡在质检环节，产线任务令 {wo_id} 等料开工"
                f"(缺口 {gap})，请优先安排检验放行，谢谢。"
            )
        return (
            f"{recipient}：物料 {mat} 被其它任务占用，任务令 {wo_id} 缺口 {gap}，"
            f"请协调释放或调整占用优先级，谢谢。"
        )
