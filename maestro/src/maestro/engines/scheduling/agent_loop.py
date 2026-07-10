"""ReAct scheduling loop orchestration."""

import asyncio
import logging

from maestro.engines.base import ProgressFn, emit_progress
from maestro.engines.scheduling.run_state import AgentStatus, RunState
from maestro.engines.scheduling.schemas import AgentResult
from maestro.engines.scheduling.termination import TerminationPolicy
from maestro.engines.scheduling.tool_executor import ConfirmResolver, ToolExecutor
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import PendingActionStore
from maestro.foundation.llm import AgentTurn, LLMClient, LLMError
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.permissions import PermissionEngine
from maestro.foundation.tools.registry import Precondition, ToolRegistry

logger = logging.getLogger(__name__)

_FORCE_FINAL = "请基于以上工具观察，直接用简洁中文给出结论与后续建议，不要再调用任何工具。"
_NUDGE = "你没有调用工具，也没有产出内容。请继续：调用工具查证事实，或直接给出结论。"
_MAX_NUDGES = 2
_LLM_RETRIES = 2

_RunState = RunState


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        pending: PendingActionStore,
        audit: AuditLog,
        system_prompt: str,
        allowed_tools: list[str],
        max_steps: int,
        observation_max_bytes: int = 8192,
        extra_preconditions: dict[str, list[Precondition]] | None = None,
        permissions: PermissionEngine | None = None,
        confirm_resolver: ConfirmResolver | None = None,
        validate_input: bool = True,
        observations: ObservationStore | None = None,
    ):
        self._llm = llm
        self._tools = tools
        self._pending = pending
        self._system = system_prompt
        self._allowed = list(allowed_tools)
        self._termination = TerminationPolicy(max_steps)
        self._executor = ToolExecutor(
            tools=tools,
            audit=audit,
            allowed_tools=allowed_tools,
            observation_max_bytes=observation_max_bytes,
            extra_preconditions=extra_preconditions,
            permissions=permissions,
            confirm_resolver=confirm_resolver,
            validate_input=validate_input,
            observations=observations,
        )

    @property
    def available(self) -> bool:
        return self._llm.available

    async def run(
        self,
        task: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> AgentResult:
        if not self._llm.available:
            raise LLMError("LLM 未配置，无法运行 ReAct 智能体")

        pending_before = {action.action_id for action in self._pending.list_pending()}
        state = RunState.start(task, history)
        openai_tools = self._tools.to_openai_tools(self._allowed)
        iteration = 0

        while state.status == AgentStatus.RUNNING:
            stop_status = self._termination.status_for(state, iteration)
            if stop_status is not None:
                state.status = stop_status
                break
            await emit_progress(on_progress, "思考中…")
            try:
                await self._step(state, openai_tools, on_progress)
            except LLMError:
                state.status = AgentStatus.ERROR
                break
            iteration += 1

        if self._termination.needs_forced_final(state.status):
            await emit_progress(on_progress, "整理结论…")
            state.answer = await self._force_final(state) or state.answer

        pending_actions = [
            action for action in self._pending.list_pending() if action.action_id not in pending_before
        ]
        return AgentResult(
            answer=state.answer or self._fallback_answer(state.steps),
            steps=state.steps,
            pending_actions=pending_actions,
            stop_reason=state.status.value,
        )

    async def _step(
        self,
        state: RunState,
        openai_tools: list[dict],
        on_progress: ProgressFn | None = None,
    ) -> None:
        turn = await self._chat_turn_resilient(state.messages, openai_tools)
        if not turn.tool_calls:
            text = turn.text.strip()
            if text:
                state.finish(turn.text)
                return
            state.request_nudge(_NUDGE, _MAX_NUDGES)
            return

        state.messages.append(turn.assistant_message)
        thought = (turn.text or "").strip()
        if thought:
            await emit_progress(on_progress, thought)

        if len(turn.tool_calls) > 1 and all(
            self._executor.parallelizable(call.name) for call in turn.tool_calls
        ):
            await self._step_concurrent(turn.tool_calls, state, turn, on_progress)
            return
        for call in turn.tool_calls:
            await self._step_one(call, state, turn, on_progress)

    async def _step_one(self, call, state: RunState, turn: AgentTurn, on_progress) -> None:
        await emit_progress(on_progress, f"调用工具 {call.name}")
        observation, blocked = await self._executor.handle_call(
            call.name, call.arguments, state, on_progress
        )
        self._record_step(state, turn, call, observation, blocked)

    async def _step_concurrent(self, calls, state: RunState, turn: AgentTurn, on_progress) -> None:
        logger.info("[AGENT] 并发执行 %d 个只读工具: %s", len(calls), [call.name for call in calls])
        await emit_progress(on_progress, f"并发执行 {len(calls)} 个只读工具")
        gated = []
        for call in calls:
            observation, tool = await self._executor.gate_call(call.name, call.arguments, state)
            gated.append((call, observation, tool))
        to_execute = [(call, tool) for call, _observation, tool in gated if tool is not None]

        async def execute(call, tool):
            await emit_progress(on_progress, f"调用工具 {call.name}")
            return await self._executor.execute_call(
                tool, call.name, call.arguments, state, on_progress
            )

        executed = await asyncio.gather(*(execute(call, tool) for call, tool in to_execute))
        results = {call.id: result for (call, _tool), result in zip(to_execute, executed)}
        for call, observation, tool in gated:
            if tool is None:
                self._record_step(state, turn, call, observation, True)
                continue
            tool_observation, blocked = results[call.id]
            self._record_step(state, turn, call, tool_observation, blocked)

    def _record_step(self, state: RunState, turn: AgentTurn, call, observation, blocked: bool) -> None:
        content, stored = self._executor.serialize_observation(observation)
        state.record_tool_step(
            thought=turn.text,
            tool=call.name,
            arguments=call.arguments,
            tool_call_id=call.id,
            content=content,
            observation=stored,
            blocked=blocked,
        )

    async def _chat_turn_resilient(
        self, messages: list[dict], tools: list[dict]
    ) -> AgentTurn:
        last_error: LLMError | None = None
        for attempt in range(_LLM_RETRIES + 1):
            try:
                return await self._llm.chat_turn(self._system, messages, tools=tools)
            except LLMError as error:
                last_error = error
                logger.warning("[AGENT] chat_turn 失败 (attempt=%d): %s", attempt, error)
        assert last_error is not None
        raise last_error

    async def _force_final(self, state: RunState) -> str:
        state.messages.append({"role": "user", "content": _FORCE_FINAL})
        try:
            final = await self._llm.chat_turn(self._system, state.messages, tools=None)
            return final.text
        except LLMError:
            return ""

    @staticmethod
    def _fallback_answer(steps) -> str:
        if not steps:
            return "未能得出结论。"
        used = ", ".join(dict.fromkeys(step.tool for step in steps))
        return f"已执行 {len(steps)} 步 (工具: {used})，但未生成最终结论，请查看处理明细。"
