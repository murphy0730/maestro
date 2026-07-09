"""ReAct 智能体循环 (推理 → 行动 → 观察)。

调度引擎的核心: 不走固定流程，而是让 LLM 在「思考→调用工具→观察结果」中自主
推进，直到给出结论。通用且与具体业务无关 (系统提示词与工具白名单由调用方注入)。

骨架参考 OpenHands `LocalConversation.run()` + `Agent.step()`，保留其「外层循环
(退出状态 → 卡死检测 → 走一步 → 硬上限)」+「单步 (调 LLM → 按响应类型三分支)」
结构，落到本平台的两触发 (对话/事件) + 两道写护栏语境:

外层循环终止态 (AgentStatus):
  FINISHED   —— 模型给出纯文本结论 (=等用户输入)，或空转达上限被收口。
  MAX_STEPS  —— 步数硬上限，强制收尾。
  STUCK      —— 卡死软检测命中 (重复动作 / 连续被护栏拦截)，强制收尾。
  ERROR      —— LLM 重试仍失败等，兜底收口 (返回已有轨迹)。

三分支单步 (step):
  TOOL_CALLS —— 走护栏执行工具，观察回喂。
  CONTENT    —— 纯文本 → FINISHED。
  EMPTY      —— 既无工具也无内容 → 纠偏 nudge 让模型继续 (有上限，防空转)。

护栏 (与 OpenHands 的「硬上限 + 软检测 + context 防护」同构):
  1. 步数硬上限 max_steps        —— 必停。
  2. 卡死软检测 StuckDetector    —— 重复动作 / 连续拦截即置 STUCK。
  3. 工具白名单                  —— 只允许白名单内工具。
  4. 写操作前置断言 precondition —— 写操作执行前过代码硬规则 (授权由工具自身 ActionGate 兜底)。
  5. LLM 抖动重试                —— chat_turn 瞬时失败重试，仍失败则收口为 ERROR。
  6. 观察截断 observation_max_bytes —— 单条工具观察回喂前限长，防大结果打爆上下文。

待确认动作通过 PendingActionStore 运行前后快照差集收集 (不与工具返回耦合)。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable

from maestro.engines.base import ProgressFn, emit_progress
from maestro.engines.scheduling.schemas import AgentResult, AgentStep
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import PendingActionStore
from maestro.foundation.llm import AgentTurn, LLMClient, LLMError
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.permissions import PermissionDecision, PermissionEngine
from maestro.foundation.tools.registry import Precondition, ToolProgress, ToolRegistry
from maestro.foundation.tools.validation import validate_arguments

logger = logging.getLogger(__name__)

# can_use_tool 的交互确认解析器: 给定 (工具名, 参数, 决策)，返回是否放行。
# 返回 None → 无人可确认，挂起为 pending (不执行)。用于把「需确认」的读/中性工具
# 接到真实 UI；缺省 (未注入) 时 "ask" 直接挂起。
ConfirmResolver = Callable[[str, dict, PermissionDecision], Awaitable[bool | None]]

_FORCE_FINAL = (
    "请基于以上工具观察，直接用简洁中文给出结论与后续建议，不要再调用任何工具。"
)
_NUDGE = "你没有调用工具，也没有产出内容。请继续：调用工具查证事实，或直接给出结论。"

_MAX_NUDGES = 2  # 连续空响应的纠偏上限，超出即收口 (防空转)
_STUCK_REPEAT = 3  # 同一 (工具, 参数) 累计出现达此次数 → 卡死
_STUCK_BLOCKED = 3  # 最近连续被护栏拦截达此步数 → 卡死
_LLM_RETRIES = 2  # chat_turn 瞬时失败的额外重试次数


class AgentStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "final"
    MAX_STEPS = "max_steps"
    STUCK = "stuck"
    ERROR = "error"


@dataclass
class _RunState:
    """一次 ReAct 运行的中心状态，循环全程读写 (对应 OpenHands 的 State)。"""

    messages: list[dict]
    steps: list[AgentStep] = field(default_factory=list)
    # (工具, 规范化参数) → 次数。读类计数在每次成功写操作后清零 (状态已变，重读正当)
    seen: dict[tuple[str, str], int] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.RUNNING
    answer: str = ""
    nudges: int = 0


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
        self._audit = audit
        self._system = system_prompt
        self._allowed = list(allowed_tools)
        self._max_steps = max_steps
        self._obs_max = observation_max_bytes
        self._extra = extra_preconditions
        # 统一权限引擎 (item⑤): None → 跳过 can_use_tool 层, 保持既有行为
        self._permissions = permissions
        # 交互确认解析器 (item④): "ask" 工具的放行入口
        self._confirm = confirm_resolver
        # 泛型输入校验开关 (item①)
        self._validate_input = validate_input
        # 观察离线暂存 (方案2): None → 保留有损截断兜底
        self._observations = observations

    @property
    def available(self) -> bool:
        return self._llm.available

    async def run(
        self,
        task: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> AgentResult:
        """跑一轮 ReAct。`history` 注入多轮上下文 (前若干轮 user/assistant 文本)。

        LLM 未配置时抛 LLMError，由引擎降级；运行中 LLM 抖动经重试仍失败则收口为 ERROR。
        """
        if not self._llm.available:
            raise LLMError("LLM 未配置，无法运行 ReAct 智能体")

        before_ids = {a.action_id for a in self._pending.list_pending()}
        st = _RunState(messages=[*(history or []), {"role": "user", "content": task}])
        openai_tools = self._tools.to_openai_tools(self._allowed)

        iteration = 0
        while st.status == AgentStatus.RUNNING:
            if iteration >= self._max_steps:  # 硬上限: 步数 (必停)
                st.status = AgentStatus.MAX_STEPS
                break
            if self._is_stuck(st):  # 软检测: 卡死
                st.status = AgentStatus.STUCK
                break
            await emit_progress(
                on_progress, "思考中…"
            )
            try:
                await self._step(st, openai_tools, on_progress)
            except LLMError:  # 重试仍失败 → 收口 (保留已有轨迹兜底)
                st.status = AgentStatus.ERROR
                break
            iteration += 1

        # 被硬上限 / 卡死强制中断的，追加一次收尾发言 (让模型基于观察给结论)
        if st.status in (AgentStatus.MAX_STEPS, AgentStatus.STUCK):
            await emit_progress(on_progress, "整理结论…")
            st.answer = await self._force_final(st) or st.answer

        new_pending = [
            a for a in self._pending.list_pending() if a.action_id not in before_ids
        ]
        return AgentResult(
            answer=st.answer or self._fallback_answer(st.steps),
            steps=st.steps,
            pending_actions=new_pending,
            stop_reason=st.status.value,
        )

    # ── 单步: 一次「思考 → 行动 → 观察」，按 LLM 响应类型三分支 ──

    async def _step(
        self,
        st: _RunState,
        openai_tools: list[dict],
        on_progress: ProgressFn | None = None,
    ) -> None:
        turn = await self._chat_turn_resilient(st.messages, openai_tools)

        if not turn.tool_calls:
            text = turn.text.strip()
            if text:  # CONTENT: 纯文本 = 结论 = 本轮结束
                st.answer = turn.text
                st.status = AgentStatus.FINISHED
                return
            # EMPTY: 既无工具也无内容 → 纠偏 nudge (有上限，防空转)
            if st.nudges >= _MAX_NUDGES:
                st.status = AgentStatus.FINISHED
                return
            st.nudges += 1
            st.messages.append({"role": "user", "content": _NUDGE})
            return

        # TOOL_CALLS: 过护栏执行，观察回喂 (超限观察截断后回喂与留痕)
        st.messages.append(turn.assistant_message)
        # 思考文本随 progress 流下发 (前端思考过程展示；不下发则思考对用户是黑盒)
        thought = (turn.text or "").strip()
        if thought:
            await emit_progress(on_progress, thought)

        calls = turn.tool_calls
        # 并发 (item③): 一轮内「全为只读/中性 + 多个」的批次并发执行; 含写或单个 →
        # 保持既有串行路径 (写操作有状态依赖, 不并发)。门控 (白名单/去重/校验/权限/
        # 断言) 始终串行, 保证 seen 计数与决策顺序确定; 仅工具执行本身并发。
        if len(calls) > 1 and all(self._parallelizable(c.name) for c in calls):
            await self._step_concurrent(calls, st, turn, on_progress)
        else:
            for call in calls:
                await self._step_one(call, st, turn, on_progress)

    async def _step_one(self, call, st, turn, on_progress) -> None:
        await emit_progress(on_progress, f"调用工具 {call.name}")
        observation, blocked = await self._handle_call(
            call.name, call.arguments, st, on_progress
        )
        self._record_step(st, turn, call, observation, blocked)

    async def _step_concurrent(self, calls, st, turn, on_progress) -> None:
        logger.info(
            "[AGENT] 并发执行 %d 个只读工具: %s", len(calls), [c.name for c in calls]
        )
        await emit_progress(on_progress, f"并发执行 {len(calls)} 个只读工具")
        # ① 门控串行 (保持 seen/校验/权限 顺序确定)
        gated = [(call, *await self._gate_call(call.name, call.arguments, st)) for call in calls]
        # ② 通过门控的读/中性工具并发执行
        to_exec = [(c, t) for c, _o, t in gated if t is not None]

        async def _run(call, tool):
            await emit_progress(on_progress, f"调用工具 {call.name}")
            return await self._execute_call(tool, call.name, call.arguments, st, on_progress)

        execed = await asyncio.gather(*[_run(c, t) for c, t in to_exec])
        results = {c.id: r for (c, _t), r in zip(to_exec, execed)}
        # ③ 按原始顺序回填 steps/messages
        for call, obs, tool in gated:
            if tool is None:
                self._record_step(st, turn, call, obs, True)
            else:
                observation, blocked = results[call.id]
                self._record_step(st, turn, call, observation, blocked)

    def _record_step(self, st, turn, call, observation, blocked) -> None:
        content, stored = self._serialize_observation(observation)
        st.steps.append(
            AgentStep(
                thought=turn.text,
                tool=call.name,
                arguments=call.arguments,
                observation=stored,
                blocked=blocked,
            )
        )
        st.messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    def _parallelizable(self, name: str) -> bool:
        """仅只读/中性且在白名单内的工具可并发 (写/白名单外走串行门控)。"""
        if name not in self._allowed:
            return False
        try:
            return self._tools.get(name).kind in ("read", "aux")
        except KeyError:
            return False

    async def _handle_call(
        self, name: str, args: dict, st: _RunState, on_progress: ProgressFn | None = None
    ) -> tuple[object, bool]:
        """串行执行一次工具调用: 先过门控, 通过则执行。返回 (观察, 是否被护栏拦截)。"""
        obs, tool = await self._gate_call(name, args, st)
        if tool is None:
            return obs, True
        return await self._execute_call(tool, name, args, st, on_progress)

    async def _gate_call(self, name: str, args: dict, st: _RunState):
        """执行前的全部门控 (串行、确定顺序)。返回 (blocked_observation, None) 被拦截，
        或 (None, tool) 放行并附待执行工具。"""
        # 护栏 3: 工具白名单
        if name not in self._allowed:
            return {"blocked": f"工具 {name} 不在调度引擎白名单内，已拒绝"}, None
        # 绕圈: 完全相同的调用 (同名同参) 计数并跳过重复执行
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        st.seen[key] = st.seen.get(key, 0) + 1
        if st.seen[key] > 1:
            return {
                "blocked": "重复的相同工具调用，已跳过 (疑似绕圈)。请基于已有观察给出结论或改换思路。"
            }, None

        tool = self._tools.get(name)

        # 护栏 (item①): 泛型输入校验 (白名单、去重之后, 执行之前)
        if self._validate_input:
            ok, reason = validate_arguments(tool.parameters, args)
            if not ok:
                self._audit.record(
                    actor="scheduling_agent",
                    action=f"invalid_input:{name}",
                    params=args,
                    result={"reason": reason},
                )
                return {"blocked": f"输入校验失败: {reason}"}, None

        # 护栏 (item④/⑤): 统一权限引擎 can_use_tool (读/写/中性一体, 叠加在 ActionGate 之上)
        if self._permissions is not None:
            decision = self._permissions.evaluate_tool(name, tool.kind, args)
            if decision.effect == "deny":
                self._audit.record(
                    actor="scheduling_agent",
                    action=f"permission_denied:{name}",
                    params=args,
                    result={"reason": decision.reason, "source": decision.source},
                )
                return {"blocked": f"权限引擎拒绝执行 {name}: {decision.reason}"}, None
            if decision.effect == "ask":
                approved = await self._ask_permission(name, args, decision)
                if approved is None:  # 无解析器 → 挂起为 pending, 不执行
                    self._audit.record(
                        actor="scheduling_agent",
                        action=f"permission_pending:{name}",
                        params=args,
                        result={"reason": decision.reason, "source": decision.source},
                    )
                    return {
                        "blocked": f"工具 {name} 需人工确认 (pending)，尚未执行。",
                        "pending_confirmation": True,
                    }, None
                if not approved:  # 用户明确拒绝
                    return {"blocked": f"用户拒绝执行 {name}"}, None

        # 护栏 4: 写操作前置断言
        if tool.kind == "write" and tool.precondition is not None:
            result = await tool.precondition(args)
            if not result.ok:
                self._audit.record(
                    actor="scheduling_agent",
                    action=f"precondition_blocked:{name}",
                    params=args,
                    result={"reason": result.reason},
                )
                return {"blocked": f"前置断言未通过: {result.reason}"}, None

        # 护栏 4b: 技能级追加断言 (只叠加, 不替换)
        if self._extra is not None:
            for pre in self._extra.get(name, []):
                result = await pre(args)
                if not result.ok:
                    self._audit.record(
                        actor="scheduling_agent",
                        action=f"skill_precondition_blocked:{name}",
                        params=args,
                        result={"reason": result.reason},
                    )
                    return {"blocked": f"技能前置断言未通过: {result.reason}"}, None

        return None, tool

    async def _ask_permission(self, name, args, decision) -> bool | None:
        if self._confirm is None:
            return None
        return await self._confirm(name, args, decision)

    async def _execute_call(self, tool, name, args, st, on_progress=None) -> tuple[object, bool]:
        """执行工具本体并处理写后清读。返回 (观察, 是否被拦截=False)。"""
        try:
            result = await self._tools.execute(
                name, args, on_progress=self._tool_progress(on_progress, name)
            )
        except Exception as e:  # noqa: BLE001 — 工具失败回喂给模型，不中断循环
            logger.warning("[AGENT] 工具 %s 执行失败: %s", name, e)
            return {"error": str(e)}, False
        if tool.kind == "write":
            # 写操作改变了世界状态，此前的读观察已过期 → 清读类计数放行重读；
            # 写类计数保留 (同参写操作仍防重，如重复催同一物料)。
            st.seen = {
                k: c for k, c in st.seen.items()
                if self._tools.get(k[0]).kind == "write"
            }
        return result, False

    def _tool_progress(self, on_progress: ProgressFn | None, name: str) -> ToolProgress | None:
        """把工具阶段事件桥接为对外的字符串 progress 帧。on_progress 缺席 → None (零开销)。"""
        if on_progress is None:
            return None

        async def _cb(event: dict) -> None:
            label = f"{name} {event.get('phase', '')}".strip()
            pct = event.get("percent")
            if pct is not None:
                label += f" {pct}%"
            msg = event.get("message")
            if msg:
                label += f": {msg}"
            await emit_progress(on_progress, label)

        return _cb

    def _serialize_observation(self, observation: object) -> tuple[str, object]:
        """序列化观察用于回喂。返回 (回喂 LLM 的字符串, 存入 AgentStep 的对象)。

        超限时: 有 ObservationStore → 整对象离线暂存, 两者统一用紧凑句柄 (方案2, 无损、
        可经 read_observation / GET 取回)；无 store → 退化为有损截断兜底。两者都保证上下文
        与 data.steps 有界 (steps 会经 SSE context 帧推给前端)。
        """
        raw = json.dumps(observation, ensure_ascii=False, default=str)
        raw_bytes = raw.encode("utf-8")
        if len(raw_bytes) <= self._obs_max:
            return raw, observation
        if self._observations is not None:
            handle = self._observations.put(observation)
            return json.dumps(handle, ensure_ascii=False), handle
        preview = raw_bytes[: self._obs_max].decode("utf-8", errors="ignore")
        truncated = {
            "truncated": True,
            "original_bytes": len(raw_bytes),
            "preview": preview,
            "hint": "结果过大已截断。请用更精确的参数缩小查询范围。",
        }
        return json.dumps(truncated, ensure_ascii=False), truncated

    # ── 卡死软检测 (对应 OpenHands StuckDetector 的高性价比子集) ──

    def _is_stuck(self, st: _RunState) -> bool:
        # 模式①: 同一 (工具, 参数) 累计出现达阈值 (重复动作打转)
        if any(c >= _STUCK_REPEAT for c in st.seen.values()):
            return True
        # 模式②: 最近连续若干步全部被护栏拦截 (反复撞墙、无有效进展)
        recent = st.steps[-_STUCK_BLOCKED:]
        if len(recent) >= _STUCK_BLOCKED and all(s.blocked for s in recent):
            return True
        return False

    # ── LLM 调用 (抖动重试) 与收尾发言 ──

    async def _chat_turn_resilient(
        self, messages: list[dict], tools: list[dict]
    ) -> AgentTurn:
        last: LLMError | None = None
        for attempt in range(_LLM_RETRIES + 1):
            try:
                return await self._llm.chat_turn(self._system, messages, tools=tools)
            except LLMError as e:
                last = e
                logger.warning("[AGENT] chat_turn 失败 (attempt=%d): %s", attempt, e)
        assert last is not None
        raise last

    async def _force_final(self, st: _RunState) -> str:
        st.messages.append({"role": "user", "content": _FORCE_FINAL})
        try:
            final = await self._llm.chat_turn(self._system, st.messages, tools=None)
            return final.text
        except LLMError:
            return ""

    @staticmethod
    def _fallback_answer(steps: list[AgentStep]) -> str:
        if not steps:
            return "未能得出结论。"
        used = ", ".join(dict.fromkeys(s.tool for s in steps))
        return f"已执行 {len(steps)} 步 (工具: {used})，但未生成最终结论，请查看处理明细。"
