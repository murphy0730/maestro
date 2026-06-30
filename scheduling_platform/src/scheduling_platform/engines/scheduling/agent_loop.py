"""ReAct 智能体循环 (推理 → 行动 → 观察)。

调度引擎的核心: 不走固定流程，而是让 LLM 在「思考→调用工具→观察结果」中自主
推进，直到给出结论。通用且与具体业务无关 (系统提示词与工具白名单由调用方注入)，
工程上钉死三类护栏:

循环护栏 (防失控):
  1. max_steps    —— 最大步数，超出强制收尾。
  2. 工具白名单    —— 只暴露/只允许调用白名单内的工具。
  3. 绕圈检测      —— 完全相同的工具调用 (同名同参) 不再重复执行。

写操作护栏 (防误写，在 _handle_call 内，授权由工具自身的 ActionGate 兜底):
  4. 前置断言      —— 写操作执行前先过 tool.precondition (代码硬规则)。

待确认动作通过 PendingActionStore 运行前后快照差集收集 (不与工具返回耦合)。
"""

import json
import logging

from scheduling_platform.engines.scheduling.schemas import AgentResult, AgentStep
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.llm import LLMClient, LLMError
from scheduling_platform.foundation.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_FORCE_FINAL = (
    "已达到最大思考步数。请基于以上工具观察，直接用简洁中文给出结论与后续建议，"
    "不要再调用任何工具。"
)


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
    ):
        self._llm = llm
        self._tools = tools
        self._pending = pending
        self._audit = audit
        self._system = system_prompt
        self._allowed = list(allowed_tools)
        self._max_steps = max_steps

    @property
    def available(self) -> bool:
        return self._llm.available

    async def run(self, task: str, history: list[dict] | None = None) -> AgentResult:
        """跑一轮 ReAct。LLM 不可用时抛 LLMError，由引擎降级。"""
        if not self._llm.available:
            raise LLMError("LLM 未配置，无法运行 ReAct 智能体")

        before_ids = {a.action_id for a in self._pending.list_pending()}
        messages: list[dict] = [*(history or []), {"role": "user", "content": task}]
        openai_tools = self._tools.to_openai_tools(self._allowed)
        steps: list[AgentStep] = []
        seen: set[tuple[str, str]] = set()  # 绕圈检测: (工具名, 规范化参数)
        answer = ""
        stop_reason = "final"

        for _ in range(self._max_steps):
            turn = await self._llm.chat_turn(self._system, messages, tools=openai_tools)
            if not turn.tool_calls:
                answer = turn.text
                break
            messages.append(turn.assistant_message)
            for call in turn.tool_calls:
                observation, blocked = await self._handle_call(call.name, call.arguments, seen)
                steps.append(
                    AgentStep(
                        thought=turn.text,
                        tool=call.name,
                        arguments=call.arguments,
                        observation=observation,
                        blocked=blocked,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(observation, ensure_ascii=False, default=str),
                    }
                )
        else:
            stop_reason = "max_steps"
            messages.append({"role": "user", "content": _FORCE_FINAL})
            try:
                final = await self._llm.chat_turn(self._system, messages, tools=None)
                answer = final.text
            except LLMError:
                answer = ""

        new_pending = [
            a for a in self._pending.list_pending() if a.action_id not in before_ids
        ]
        return AgentResult(
            answer=answer or self._fallback_answer(steps),
            steps=steps,
            pending_actions=new_pending,
            stop_reason=stop_reason,
        )

    async def _handle_call(
        self, name: str, args: dict, seen: set[tuple[str, str]]
    ) -> tuple[object, bool]:
        """执行一次工具调用，返回 (观察, 是否被护栏拦截)。"""
        # 护栏 2: 工具白名单
        if name not in self._allowed:
            return {"blocked": f"工具 {name} 不在调度引擎白名单内，已拒绝"}, True
        # 护栏 3: 绕圈检测
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if key in seen:
            return {
                "blocked": "重复的相同工具调用，已跳过 (疑似绕圈)。请基于已有观察给出结论或改换思路。"
            }, True
        seen.add(key)

        tool = self._tools.get(name)
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
                return {"blocked": f"前置断言未通过: {result.reason}"}, True

        try:
            return await self._tools.execute(name, args), False
        except Exception as e:  # noqa: BLE001 — 工具失败回喂给模型，不中断循环
            logger.warning("[AGENT] 工具 %s 执行失败: %s", name, e)
            return {"error": str(e)}, False

    @staticmethod
    def _fallback_answer(steps: list[AgentStep]) -> str:
        if not steps:
            return "未能得出结论。"
        used = ", ".join(dict.fromkeys(s.tool for s in steps))
        return f"已执行 {len(steps)} 步 (工具: {used})，但未生成最终结论，请查看处理明细。"
