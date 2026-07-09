"""调度引擎 — ReAct 智能体 (v0.2)。

双触发 (对话 + 事件) 复用同一个 ReAct 循环: 事件不再硬映射到固定流程，而是被
翻译成一段「初始任务描述」唤醒智能体，由它自主推理该查什么、催不催、要不要
下发或通知 (写操作受前置断言 + 授权两道护栏约束)。

LLM 不可用时降级: 给出确定性的齐套总览 (不臆造)，保证基本可用与可测。
"""

import logging

from maestro.domain.models import KittingResult, SystemEvent
from maestro.engines.base import Engine, EngineResponse, ProgressFn
from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.engines.scheduling.schemas import AgentResult
from maestro.foundation.audit import AuditLog
from maestro.foundation.kitting import KittingService
from maestro.foundation.llm import LLMError

logger = logging.getLogger(__name__)

SCHEDULING_SYSTEM = """你是制造企业的生产调度智能体，目标是保障订单按期、产线不停。
你以「思考 → 调用工具 → 观察结果」的方式自主推进，直到能给出结论。

工作原则:
- 先用只读工具把事实查清 (齐套/库存/任务令/缺料归因/异常影响)，再决定是否动手。
- 缺料: 先 check_kitting 确认，再 analyze_material_shortage 归因，必要时
  send_expedite_message 催料 (尽量带 material_id；内部自动发，供应商需人确认)。
- 下发: 用 dispatch_work_order (要求已齐套、产线可用，需人确认)。
- 异常: 先 classify_exception 定级，analyze_exception_impact 评估影响，
  再 notify_personnel 通知，关键决策留给人。
- 不要臆造数据，一切以工具返回为准；写操作被前置断言/授权拦截时，如实说明原因。
- 工具结果过大时会离线暂存并返回 observation_ref (含规模/字段/预览)；需要细节时用
  read_observation(ref, offset, limit) 分页取回，切勿臆造未取回的内容。
- 收尾时用简洁中文给出: 结论、已采取/待确认的动作、建议的后续。"""


class SchedulingEngine(Engine):
    name = "scheduling"

    def __init__(self, agent: AgentLoop, kitting: KittingService, audit: AuditLog):
        self._agent = agent
        self._kitting = kitting
        self._audit = audit

    # ── 对话触发 ─────────────────────────────────────────────

    async def handle_chat(
        self,
        message: str,
        entities: dict,
        session_id: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> EngineResponse:
        if not self._agent.available:
            return await self._degraded(entities.get("wo_ids"))
        try:
            result = await self._agent.run(message, history=history, on_progress=on_progress)
        except LLMError:
            return await self._degraded(entities.get("wo_ids"))
        return self._to_response(result)

    # ── 事件触发 (事件→任务描述→唤醒同一个 ReAct 循环) ─────────

    async def handle_event(self, event: SystemEvent) -> EngineResponse:
        logger.info("[SCHED-ENGINE] 被事件唤醒: %s %s", event.type, event.payload)
        self._audit.record(
            actor="event_layer",
            action=f"engine_wakeup:{event.type}",
            params={"event_id": event.event_id, "payload": event.payload},
        )
        if not self._agent.available:
            return await self._degraded(self._event_wo_ids(event))
        try:
            result = await self._agent.run(self._event_task(event))
        except LLMError:
            return await self._degraded(self._event_wo_ids(event))
        return self._to_response(result)

    # ── 内部 ─────────────────────────────────────────────────

    @staticmethod
    def _to_response(result: AgentResult) -> EngineResponse:
        return EngineResponse(
            reply=result.answer,
            data={
                "steps": [s.model_dump(mode="json") for s in result.steps],
                "stop_reason": result.stop_reason,
            },
            pending_actions=result.pending_actions,
        )

    @staticmethod
    def _event_wo_ids(event: SystemEvent) -> list[str] | None:
        payload = event.payload
        return payload.get("wo_ids") or payload.get("affected_wo_ids") or (
            [payload["wo_id"]] if payload.get("wo_id") else None
        )

    def _event_task(self, event: SystemEvent) -> str:
        """把系统事件翻译成唤醒智能体的初始任务描述。"""
        payload = event.payload
        wo_ids = self._event_wo_ids(event)
        wo_hint = f" 相关任务令: {', '.join(wo_ids)}。" if wo_ids else ""
        if event.type == "material_shortage_warning":
            return (
                f"收到缺料预警 (来源 {payload.get('source', '未知')})。{wo_hint}"
                "请核查相关任务令的齐套情况、定位缺料卡在哪一环，并按需发起催料。"
            )
        if event.type == "equipment_alarm":
            desc = payload.get("description", "设备报警")
            return (
                f"收到设备报警: {desc}。{wo_hint}"
                "请评估对生产/交期的影响，并提出处置 (必要时通知相关人员到场)。"
            )
        if event.type == "quality_issue":
            desc = payload.get("description", "质量异常")
            return (
                f"收到质量异常: {desc}。{wo_hint}"
                "请评估影响范围与交期威胁，并提出处置建议。"
            )
        return f"收到系统事件 {event.type}: {payload}。请评估是否需要处置。"

    async def _degraded(self, wo_ids: list[str] | None) -> EngineResponse:
        """LLM 不可用时的确定性降级: 只给齐套总览，不臆造后续动作。"""
        results = await self._kitting.check(wo_ids)
        return EngineResponse(
            reply=(
                self._kitting_summary(results)
                + "\n\n(智能体当前不可用，仅提供齐套总览；催料/下发/异常处置暂不可用。)"
            ),
            data={"kitting": [r.model_dump(mode="json") for r in results]},
        )

    @staticmethod
    def _kitting_summary(results: list[KittingResult]) -> str:
        if not results:
            return "没有找到待检查的任务令。"
        lines = [f"齐套检查完成，共 {len(results)} 个任务令:"]
        for r in results:
            if r.is_kitted:
                lines.append(f"- {r.wo_id}: ✓ 齐套")
            else:
                missing = ", ".join(
                    f"{s.material_name or s.material_id} 缺 {s.shortage_qty:g}{s.unit}"
                    for s in r.shortages
                )
                eta = f" (预计 {r.estimated_ready_date} 齐套)" if r.estimated_ready_date else ""
                lines.append(f"- {r.wo_id}: ✗ 缺料 — {missing}{eta}")
        return "\n".join(lines)
