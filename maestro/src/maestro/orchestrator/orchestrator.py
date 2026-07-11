"""统一入口主类。

接收用户输入 → 路由判断意图 → 调用对应引擎 → 返回结果。
低置信度 / 歧义时返回带选项的澄清问题，不瞎猜。
"""

import logging

from maestro.config import Settings
from maestro.engines.base import Engine, EngineResponse, ProgressFn, emit_progress
from maestro.engines.query.query_engine import QueryEngine
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import ActionGate
from maestro.foundation.exec_context import ExecMode, use_mode
from maestro.foundation.memory import ConversationMemory
from maestro.orchestrator.router import IntentRouter, extract_entities
from maestro.orchestrator.schemas import ChatResponse, RouteDecision
from maestro.skills.engine import SkillEngine

logger = logging.getLogger(__name__)

CLARIFY_REPLY = (
    "我不太确定你的意图，想让我做哪个？请直接回复序号 (1/2/3) 或关键词:\n"
    "① 重新排产 —— 重新求解这批订单的生产计划\n"
    "② 调度执行 —— 查齐套/催料/下发任务令/处置异常\n"
    "③ 只是查数据 —— 订单/库存/任务令状态查询"
)
CLARIFY_OPTIONS = ["重新排产(排产引擎)", "调度执行: 齐套/催料/下发/异常(调度引擎)", "数据查询"]

# 澄清选项 → 意图: 序号与关键词都可命中，命中后直接路由 (不再走嵌入/LLM)
CLARIFY_INTENTS: list[tuple[str, set[str], tuple[str, ...]]] = [
    ("planning", {"1", "①", "一"}, ("排产", "重排", "排程", "排计划", "排一下")),
    ("scheduling", {"2", "②", "二"}, ("调度", "催", "齐套", "缺料", "下发", "任务令", "异常", "报警")),
    ("query", {"3", "③", "三"}, ("查", "查询", "查数据", "看")),
]


def resolve_clarification(reply: str) -> str | None:
    """把用户对澄清的回复解析为意图；无法判定返回 None (按新请求重新路由)。"""
    text = reply.strip()
    for intent, tokens, keywords in CLARIFY_INTENTS:
        if text in tokens or any(k in text for k in keywords):
            return intent
    return None

class Orchestrator:
    def __init__(
        self,
        router: IntentRouter,
        planning_engine: Engine,
        scheduling_engine: Engine,
        query_engine: QueryEngine,
        memory: ConversationMemory,
        audit: AuditLog,
        gate: ActionGate,
        settings: Settings,
        skill_engine: SkillEngine,
    ):
        self._router = router
        self._planning = planning_engine
        self._scheduling = scheduling_engine
        self._query = query_engine
        self._memory = memory
        self._audit = audit
        self._gate = gate
        self._settings = settings
        self._skills = skill_engine

    async def handle(
        self,
        session_id: str,
        message: str,
        route: str = "auto",
        on_progress: ProgressFn | None = None,
        skill_ids: list[str] | None = None,
        mode: ExecMode = "plan",
    ) -> ChatResponse:
        """三个引擎 + 技能引擎的唯一入口，故在此把执行模式注入 contextvar，
        由下游 ActionGate.request 读取。不经 HTTP 的调用 (CLI/事件) 取默认 "plan"。
        """
        with use_mode(mode):
            return await self._handle(session_id, message, route, on_progress, skill_ids)

    async def _handle(
        self,
        session_id: str,
        message: str,
        route: str = "auto",
        on_progress: ProgressFn | None = None,
        skill_ids: list[str] | None = None,
    ) -> ChatResponse:
        state = self._memory.get(session_id)

        # ── 前端选定技能 (skill_ids 非空)：跳过路由，直接派发到 SkillEngine ──
        if skill_ids:
            decision = RouteDecision(
                intent="skill",
                skill_id=skill_ids[0],
                skill_ids=list(skill_ids),
                confidence=1.0,
                entities=extract_entities(message),
                reason="前端选定技能",
                route_method="forced",
            )
            self._memory.append(session_id, "user", message)
            self._record_route(session_id, message, decision)
            resp = await self._dispatch(decision, message, session_id, state, on_progress)
            return self._finish(session_id, decision, resp)

        # ── 前端指定引擎 (route≠auto)：跳过路由，直接派发 (支持"选定调度引擎"多轮对话) ──
        if route in ("planning", "scheduling", "query"):
            decision = RouteDecision(
                intent=route,  # type: ignore[arg-type]
                confidence=1.0,
                entities=extract_entities(message),
                reason="前端指定引擎，直接路由",
                route_method="forced",
            )
            self._memory.append(session_id, "user", message)
            self._record_route(session_id, message, decision)
            resp = await self._dispatch(decision, message, session_id, state, on_progress)
            return self._finish(session_id, decision, resp)

        # ── 澄清后处理 (设计文档 5.2 第 3 层)：选项式不重跑、开放式回 LLM ──
        skip_embedding = False
        pending = state.context.get("pending_clarification")
        if pending:
            self._memory.set_context(session_id, "pending_clarification", None)
            intent = resolve_clarification(message)
            if intent and len(message.strip()) <= 4:
                # 选项式回答 → 直接按所选选项路由原请求，不再跑嵌入/LLM
                return await self._route_clarified(
                    session_id, pending["message"], intent, state, on_progress
                )
            # 开放式回答 → 合并上下文，回到第 2 层 LLM 分类 (跳过嵌入)
            skip_embedding = True

        # ── 正常路由: 嵌入 → LLM → (低置信澄清) ───────────────
        await emit_progress(on_progress, "识别意图…")
        decision = await self._router.route(
            message, state.history, state.current_engine, skip_embedding=skip_embedding
        )
        self._memory.append(session_id, "user", message)
        self._record_route(session_id, message, decision)
        return await self._gate_and_dispatch(session_id, message, decision, state, on_progress)

    async def _route_clarified(
        self,
        session_id: str,
        original: str,
        intent: str,
        state,
        on_progress: ProgressFn | None = None,
    ) -> ChatResponse:
        decision = RouteDecision(
            intent=intent,  # type: ignore[arg-type]
            confidence=1.0,
            entities=extract_entities(original),
            reason="用户澄清后直接路由",
            route_method="clarified",
        )
        self._memory.append(session_id, "user", f"(澄清选择→{intent})")
        self._record_route(session_id, original, decision, clarified_from=original)
        resp = await self._dispatch(decision, original, session_id, state, on_progress)
        return self._finish(session_id, decision, resp)

    async def _gate_and_dispatch(
        self,
        session_id: str,
        message: str,
        decision: RouteDecision,
        state,
        on_progress: ProgressFn | None = None,
    ) -> ChatResponse:
        threshold = self._settings.route_confidence_threshold
        if decision.intent in ("planning", "scheduling", "query", "skill") and decision.confidence >= threshold:
            resp = await self._dispatch(decision, message, session_id, state, on_progress)
        else:
            # 低置信 / ambiguous → 带选项澄清，并记下原请求供澄清后直接路由
            self._memory.set_context(session_id, "pending_clarification", {"message": message})
            resp = EngineResponse(
                reply=CLARIFY_REPLY,
                needs_clarification=True,
                clarification_options=CLARIFY_OPTIONS,
            )
        return self._finish(session_id, decision, resp)

    async def _dispatch(
        self,
        decision: RouteDecision,
        message: str,
        session_id: str,
        state,
        on_progress: ProgressFn | None = None,
    ) -> EngineResponse:
        """按意图把请求派发到对应引擎/查询处理器 (正常路由与澄清后路由共用)。"""
        if decision.intent == "planning":
            self._memory.set_engine(session_id, "planning")
            return await self._planning.handle_chat(
                message, decision.entities, session_id, on_progress=on_progress
            )
        if decision.intent == "scheduling":
            self._memory.set_engine(session_id, "scheduling")
            # 历史已含本轮用户消息，去掉末条作为多轮上下文注入 ReAct
            return await self._scheduling.handle_chat(
                message,
                decision.entities,
                session_id,
                history=state.history[:-1],
                on_progress=on_progress,
            )
        if decision.intent == "skill":
            # 技能不拥有 Context Panel，不调 set_engine；历史去掉末条作上下文。
            # 前端强制指定 (forced) 受 user_invocable 约束，路由命中不受。
            return await self._skills.handle(
                decision.skill_ids or ([decision.skill_id] if decision.skill_id else []),
                message, session_id,
                history=state.history[:-1], on_progress=on_progress,
                source="user" if decision.route_method == "forced" else "route",
            )
        # query: 历史已含本轮用户消息，去掉末条作为上下文
        return await self._query.handle(message, state.history[:-1], on_progress=on_progress)

    def _record_route(
        self, session_id: str, message: str, decision: RouteDecision, clarified_from: str | None = None
    ) -> None:
        params = {"message": message}
        if clarified_from is not None:
            params["clarified_from"] = clarified_from
        self._audit.record(
            actor=session_id,
            action="route",
            params=params,
            result={
                "intent": decision.intent,
                "skill_id": decision.skill_id,
                "confidence": decision.confidence,
                "method": decision.route_method,
                "reason": decision.reason,
            },
        )

    def _finish(self, session_id: str, decision: RouteDecision, resp: EngineResponse) -> ChatResponse:
        self._memory.append(session_id, "assistant", resp.reply)
        return ChatResponse(
            reply=resp.reply,
            route=decision,
            pending_actions=resp.pending_actions,
            data=resp.data,
            needs_clarification=resp.needs_clarification,
            options=resp.clarification_options,
        )

    async def resume_clarification(
        self,
        session_id: str,
        route_to: str,
        on_progress: ProgressFn | None = None,
        mode: ExecMode = "plan",
    ) -> ChatResponse:
        """澄清回选 (前端 /chat/clarify)：按所选引擎直接路由暂存的原请求。"""
        with use_mode(mode):
            state = self._memory.get(session_id)
            pending = state.context.get("pending_clarification")
            original = pending["message"] if pending else ""
            self._memory.set_context(session_id, "pending_clarification", None)
            return await self._route_clarified(
                session_id, original, route_to, state, on_progress
            )

    async def confirm(self, session_id: str, action_id: str, approved: bool) -> ChatResponse:
        """确认/拒绝一个待执行动作。"""
        try:
            action, result = await self._gate.confirm(action_id, approved, actor=session_id)
        except (KeyError, ValueError) as e:
            return ChatResponse(reply=f"确认失败: {e}")
        if not approved:
            reply = f"已取消动作: {action.description}"
            self._memory.append(session_id, "assistant", reply, kind="system")
        elif result and result.success:
            detail = self._format_confirm_detail(action.action_type, result.detail)
            reply = f"**已执行** · {action.description}\n\n{detail}"
            # kind=normal → 前台渲染为 Markdown 气泡（非居中细行），脚本输出/产物可读。
            self._memory.append(session_id, "assistant", reply, kind="normal")
        else:
            detail = result.detail if result else action.failure_reason or "未知错误"
            reply = f"执行失败: {action.description} — {detail}"
            self._memory.append(session_id, "assistant", reply, kind="system")
        return ChatResponse(reply=reply, pending_actions=[action])

    @staticmethod
    def _format_confirm_detail(action_type: str, raw_detail: str) -> str:
        """把动作执行结果格式化为面向用户的文本。技能脚本的 JSON detail 转 Markdown。"""
        if action_type == "run_skill_script":
            import json

            from maestro.skills.script_execution import format_skill_result_markdown

            try:
                return format_skill_result_markdown(json.loads(raw_detail))
            except (json.JSONDecodeError, TypeError):
                return raw_detail
        return raw_detail
