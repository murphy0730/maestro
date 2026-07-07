"""SkillEngine — 组装 AgentLoop 执行单个技能包。

不实现 Engine ABC (签名多 skill_id；由 Orchestrator 直接持有，与 QueryEngine 同待遇)。
技能不拥有 Context Panel，不调 memory.set_engine。

护栏装配:
  - allowed_tools: meta.allowed_tools (HTTP 层 Task 2.2 在导入时已解析，运行时不为 None)。
  - file_count > 0 时追加 "read_skill_file" 到白名单。
  - extra_preconditions: 由 meta.tool_preconditions (dict[str, list[str]] 命名断言名)
    装配，查表 self._named[name] 得到 Precondition；缺省 {} → None (AgentLoop 行为不变)。
"""

from __future__ import annotations

from typing import Literal

from maestro.engines.base import EngineResponse, ProgressFn
from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import PendingActionStore
from maestro.foundation.llm import LLMClient, LLMError
from maestro.foundation.tools.registry import ToolRegistry, Precondition
from maestro.skills.store import SkillStore

SKILL_PREAMBLE = (
    "你是技能执行体。严格按下方 SKILL.md 正文步骤推进，只用允许的工具查证/操作，"
    "不要臆造数据；写操作被护栏拦截时如实说明原因。\n\n---\n\n"
)


class SkillEngine:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        pending: PendingActionStore,
        audit: AuditLog,
        store: SkillStore,
        settings,
        named_preconditions: dict[str, Precondition],
    ):
        self._llm = llm
        self._tools = tools
        self._pending = pending
        self._audit = audit
        self._store = store
        self._settings = settings
        self._named = named_preconditions

    async def handle(
        self,
        skill_ids: list[str],
        message: str,
        session_id: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
        source: Literal["user", "route"] = "user",
    ) -> EngineResponse:
        """source: 触发来源。"user"=前端强制指定（每个技能都受 user_invocable 约束）；
        "route"=路由命中。多技能：合并 allowed_tools/tool_preconditions/正文，单次 AgentLoop。"""
        if not skill_ids:
            return EngineResponse(reply="未指定技能")
        metas = []
        for sid in skill_ids:
            meta = self._store.get(sid)
            if meta is None:
                return EngineResponse(reply=f"技能 {sid} 不存在或已被删除")
            metas.append(meta)
        if source == "user":
            blocked = [m.effective_display_name for m in metas if not m.user_invocable]
            if blocked:
                return EngineResponse(
                    reply=f"技能 {'、'.join(blocked)} 不支持手动指定，仅由系统自动路由调用"
                )
        if not self._llm.available:
            return EngineResponse(reply="LLM 未配置，技能暂不可用")

        allowed: list[str] = []
        for m in metas:
            for t in (m.allowed_tools or []):
                if t not in allowed:
                    allowed.append(t)
        if any(m.file_count > 0 for m in metas) and "read_skill_file" not in allowed:
            allowed.append("read_skill_file")

        extra: dict[str, list[Precondition]] = {}
        for m in metas:
            for tool, names in m.tool_preconditions.items():
                bucket = extra.setdefault(tool, [])
                for n in names:
                    p = self._named[n]
                    if p not in bucket:
                        bucket.append(p)

        bodies: list[str] = []
        for sid, m in zip(skill_ids, metas):
            try:  # 与删除并发的竞态: 与"不存在"同口径收口
                body = self._store.get_body(sid)
            except (KeyError, FileNotFoundError):
                return EngineResponse(reply=f"技能 {sid} 不存在或已被删除")
            bodies.append(f"## 技能: {m.effective_display_name}\n\n{body}")
        combined = SKILL_PREAMBLE + "\n\n---\n\n".join(bodies)

        try:
            result = await AgentLoop(
                self._llm, self._tools, self._pending, self._audit,
                combined, allowed, self._settings.react_max_steps,
                observation_max_bytes=self._settings.react_observation_max_bytes,
                extra_preconditions=extra or None,
            ).run(message, history=history, on_progress=on_progress)
        except LLMError:
            return EngineResponse(reply="LLM 调用失败，技能暂不可用")
        return EngineResponse(
            reply=result.answer,
            data={
                "steps": [s.model_dump(mode="json") for s in result.steps],
                "stop_reason": result.stop_reason,
                "skill_ids": list(skill_ids),
            },
            pending_actions=result.pending_actions,
        )
