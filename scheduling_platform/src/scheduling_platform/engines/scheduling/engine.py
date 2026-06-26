"""调度引擎 — 双触发 (对话 + 事件)，两条路径复用同一套 workflow。"""

import logging
import re

from scheduling_platform.domain.models import (
    KittingResult,
    ProductionException,
    SystemEvent,
)
from scheduling_platform.engines.base import Engine, EngineResponse
from scheduling_platform.engines.scheduling.schemas import ExpeditingOutcome
from scheduling_platform.engines.scheduling.workflows.dispatch import DispatchWorkflow
from scheduling_platform.engines.scheduling.workflows.exception import ExceptionWorkflow
from scheduling_platform.engines.scheduling.workflows.expediting import ExpeditingWorkflow
from scheduling_platform.engines.scheduling.workflows.kitting import KittingWorkflow
from scheduling_platform.foundation.audit import AuditLog

logger = logging.getLogger(__name__)


class SchedulingEngine(Engine):
    name = "scheduling"

    def __init__(
        self,
        kitting: KittingWorkflow,
        expediting: ExpeditingWorkflow,
        dispatch: DispatchWorkflow,
        exception: ExceptionWorkflow,
        audit: AuditLog,
    ):
        self._kitting = kitting
        self._expediting = expediting
        self._dispatch = dispatch
        self._exception = exception
        self._audit = audit

    # ── 对话触发 ─────────────────────────────────────────────

    async def handle_chat(self, message: str, entities: dict, session_id: str) -> EngineResponse:
        wo_ids = entities.get("wo_ids") or re.findall(r"WO-\d+", message) or None

        if "下发" in message:
            return await self._do_dispatch(wo_ids)
        if any(k in message for k in ("异常", "报警", "停机", "故障", "坏了")):
            exc = ProductionException(
                source="user", description=message, affected_wo_ids=wo_ids or []
            )
            return await self._do_exception(exc)
        if "催" in message:
            results = await self._kitting.check(wo_ids)
            return await self._do_expedite(results)
        if any(k in message for k in ("齐套", "缺料", "料齐", "齐不齐", "开不了工")):
            results = await self._kitting.check(wo_ids)
            return EngineResponse(
                reply=self._kitting_summary(results),
                data={"kitting": [r.model_dump(mode="json") for r in results]},
            )
        # 默认: 给齐套总览 + 能力提示
        results = await self._kitting.check(wo_ids)
        return EngineResponse(
            reply=(
                self._kitting_summary(results)
                + "\n\n我还可以: 催料(「帮我催一下」)、下发任务令(「把xx下发了」)、处置异常(「2号线报警了」)。"
            ),
            data={"kitting": [r.model_dump(mode="json") for r in results]},
        )

    # ── 事件触发 (由事件层唤醒, 复用同一套 workflow) ───────────

    async def handle_event(self, event: SystemEvent) -> EngineResponse:
        logger.info("[SCHED-ENGINE] 被事件唤醒: %s %s", event.type, event.payload)
        self._audit.record(
            actor="event_layer",
            action=f"engine_wakeup:{event.type}",
            params={"event_id": event.event_id, "payload": event.payload},
        )
        if event.type == "material_shortage_warning":
            wo_ids = event.payload.get("wo_ids") or (
                [event.payload["wo_id"]] if event.payload.get("wo_id") else None
            )
            results = await self._kitting.check(wo_ids)
            return await self._do_expedite(results)
        if event.type in ("equipment_alarm", "quality_issue"):
            exc = ProductionException(
                type="equipment" if event.type == "equipment_alarm" else "quality",
                source=f"event:{event.event_id}",
                description=event.payload.get("description", event.type),
                affected_wo_ids=event.payload.get("affected_wo_ids", []),
            )
            return await self._do_exception(exc)
        logger.info("[SCHED-ENGINE] 未订阅的事件类型 %s，忽略", event.type)
        return EngineResponse(reply=f"事件 {event.type} 无对应处理流程，已忽略")

    # ── 内部编排 ─────────────────────────────────────────────

    async def _do_expedite(self, kitting_results: list[KittingResult]) -> EngineResponse:
        outcome = await self._expediting.run(kitting_results)
        return EngineResponse(
            reply=self._expedite_summary(kitting_results, outcome),
            data={
                "kitting": [r.model_dump(mode="json") for r in kitting_results],
                "expedite_records": [r.model_dump() for r in outcome.records],
            },
            pending_actions=outcome.pending_actions,
        )

    async def _do_dispatch(self, wo_ids: list[str] | None) -> EngineResponse:
        outcome = await self._dispatch.run(wo_ids)
        lines = []
        if outcome.pending_actions:
            lines.append(f"可下发 {len(outcome.pending_actions)} 个任务令 (下发需人确认):")
            lines += [f"- [{a.action_id}] {a.description}" for a in outcome.pending_actions]
        if outcome.blocked:
            lines.append(f"被拦截 {len(outcome.blocked)} 个:")
            lines += [f"- {b['wo_id']}: {'; '.join(b['reasons'])}" for b in outcome.blocked]
        if not lines:
            lines.append("没有找到符合条件的任务令。")
        return EngineResponse(
            reply="\n".join(lines),
            data={"blocked": outcome.blocked},
            pending_actions=outcome.pending_actions,
        )

    async def _do_exception(self, exc: ProductionException) -> EngineResponse:
        case = await self._exception.handle(exc)
        assessment = case["assessment"]
        lines = [
            f"异常 {exc.exception_id} 分诊: 类型={assessment['type']}, 紧急度={assessment['severity']}",
            f"受影响任务令: {', '.join(case['affected_work_orders']) or '无/待确认'}",
        ]
        if case["threatened_orders"]:
            lines.append(
                "受威胁交期订单: "
                + ", ".join(f"{o['order_id']}(交期{o['due_date']})" for o in case["threatened_orders"])
            )
        lines.append("候选处置方案 (请选择，关键决策需人确认):")
        lines += [f"  {i+1}. {p}" for i, p in enumerate(case["proposals"])]
        pending = case["pending_actions"]
        if pending:
            lines += [f"待确认通知: [{a.action_id}] {a.description}" for a in pending]
        return EngineResponse(
            reply="\n".join(lines),
            data={k: v for k, v in case.items() if k != "pending_actions"},
            pending_actions=pending,
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

    @staticmethod
    def _expedite_summary(
        kitting_results: list[KittingResult], outcome: ExpeditingOutcome
    ) -> str:
        not_kitted = [r for r in kitting_results if not r.is_kitted]
        if not not_kitted:
            return "所有任务令均已齐套，无需催料。"
        sent = [r for r in outcome.records if r.status == "sent"]
        pending = [r for r in outcome.records if r.status == "pending_confirmation"]
        lines = [f"缺料任务令 {len(not_kitted)} 个，已发起催料:"]
        if sent:
            lines.append(f"已自动催 {len(sent)} 条 (内部):")
            lines += [f"- → {r.recipient}: {r.material_name or r.material_id} ({r.stage})" for r in sent]
        if pending:
            lines.append(f"待确认 {len(pending)} 条 (供应商等外部对象，需你确认后发送):")
            lines += [f"- [{r.action_id}] → {r.recipient}: {r.content}" for r in pending]
        return "\n".join(lines)
