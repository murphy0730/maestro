"""SkillEngine — 组装 AgentLoop 执行技能包 (支持有界嵌套)。

不实现 Engine ABC (签名多 skill_id；由 Orchestrator 直接持有，与 QueryEngine 同待遇)。
技能不调 memory.set_engine；Context Panel 由 chat 层以 engine="skill" 帧驱动。

护栏装配:
  - allowed_tools: meta.allowed_tools。file_count>0 时追加 read_skill_file/list_skill_files。
  - extra_preconditions: 由 meta.tool_preconditions (命名断言) 装配。
  - 合并总量: 多技能拼接后若超 skill_prompt_max_bytes 直接报错 (不静默截断)。
  - 作用域/嵌套: 运行前 set_context 携带 allowed_skills/depth/visited/共享 Budget;
    附件工具据此只访问当前技能;invoke_nested 有界递归 (深度/环/预算)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from maestro.engines.base import EngineResponse, ProgressFn, emit_progress
from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.engines.scheduling.run_state import Budget
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import PendingActionStore
from maestro.foundation.llm import LLMClient, LLMError
from maestro.foundation.tools.registry import Precondition, ToolRegistry
from maestro.skills.context import (
    SkillInvocationContext,
    current_context,
    reset_context,
    set_context,
)
from maestro.skills.store import SkillStore

SKILL_PREAMBLE = (
    "你是技能执行体。严格按下方 SKILL.md 正文步骤推进，只用允许的工具查证/操作，"
    "不要臆造数据；写操作被护栏拦截时如实说明原因。"
    "用户未提供的业务指标、日期、人名、电话和联系方式不得虚构；"
    "必须使用‘待填写’等占位文字，或明确标注为示例数据。\n\n---\n\n"
)

_CREATE_PPT_RE = re.compile(
    r"(?:生成|制作|创建|新建|写一份|做一份|帮我做).*?(?:pptx?|幻灯片|演示文稿)"
    r"|(?:create|make|build|generate).*?(?:pptx?|slides?|presentation)",
    re.IGNORECASE,
)
_EXECUTABLE_SUFFIXES = {".py", ".js"}


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
        observations=None,
    ):
        self._llm = llm
        self._tools = tools
        self._pending = pending
        self._audit = audit
        self._store = store
        self._settings = settings
        self._named = named_preconditions
        self._observations = observations

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
        requested_skill_ids = list(skill_ids)
        skill_ids = self._resolve_creation_fallback(skill_ids, message)
        if skill_ids != requested_skill_ids:
            await emit_progress(
                on_progress,
                "所选 PPTX 技能不含整套新建入口，已切换到兼容的 PPT 生成技能。",
            )
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

        # top-level 调用上下文: 可访问本次全部技能的附件、深度 0、共享一份新预算
        # (全链路 = 单循环上限 × (最大深度+1)，故单技能不嵌套时循环自身 max_steps 先触顶)。
        budget = Budget(self._settings.react_max_steps * (self._settings.skill_max_depth + 1))
        ctx = SkillInvocationContext(
            allowed_skills=frozenset(skill_ids),
            depth=0,
            visited=frozenset(skill_ids),
            budget=budget,
        )
        return await self._run(skill_ids, message, history, on_progress, ctx)

    async def invoke_nested(
        self, skill_id: str, task: str, on_progress: ProgressFn | None = None
    ) -> dict:
        """invoke_skill 工具入口: 有界递归调用另一技能，返回观察 dict 回喂父循环。

        有界护栏: 技能存在 + 未禁用模型调用 + 环检测 + 深度上限；子技能用**自己**的
        allowed_tools、只能访问**自己**的附件、与父共享同一预算。"""
        ctx = current_context()
        if ctx is None:
            return {"blocked": "invoke_skill 仅在技能执行体内可用"}
        meta = self._store.get(skill_id)
        if meta is None:
            return {"blocked": f"技能 {skill_id} 不存在"}
        if meta.disable_model_invocation:
            return {"blocked": f"技能 {skill_id} 已禁用模型调用，不可被 invoke_skill 调用"}
        if skill_id in ctx.visited:
            return {"blocked": f"检测到技能调用环 ({skill_id} 已在祖先链)，已拒绝"}
        if ctx.depth + 1 > self._settings.skill_max_depth:
            return {"blocked": f"技能嵌套过深 (>{self._settings.skill_max_depth})，已拒绝"}
        child = SkillInvocationContext(
            allowed_skills=frozenset({skill_id}),
            depth=ctx.depth + 1,
            visited=ctx.visited | {skill_id},
            budget=ctx.budget,
        )
        resp = await self._run([skill_id], task, None, on_progress, child)
        return {
            "skill_id": skill_id,
            "answer": resp.reply,
            "stop_reason": resp.data.get("stop_reason"),
        }

    async def _run(
        self,
        skill_ids: list[str],
        message: str,
        history: list[dict] | None,
        on_progress: ProgressFn | None,
        ctx: SkillInvocationContext,
    ) -> EngineResponse:
        metas = []
        for sid in skill_ids:
            meta = self._store.get(sid)
            if meta is None:
                return EngineResponse(reply=f"技能 {sid} 不存在或已被删除")
            metas.append(meta)

        allowed: list[str] = []
        for m in metas:
            for t in (m.allowed_tools or []):
                if t not in allowed:
                    allowed.append(t)
        if any(m.file_count > 0 for m in metas):
            for t in ("read_skill_file", "list_skill_files"):
                if t not in allowed:
                    allowed.append(t)
        if any(m.scripts for m in metas) and "run_skill_script" not in allowed:
            allowed.append("run_skill_script")
        # 大观察离线暂存的配套读取工具: 任何工具结果超限都会被暂存并回喂
        # read_observation 分页提示，它是只读基础设施，不要求技能作者声明。
        if "read_observation" not in allowed:
            allowed.append("read_observation")

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
        combined = (
            SKILL_PREAMBLE
            + "\n\n---\n\n".join(bodies)
            + self._file_manifest(skill_ids, metas)
            + self._script_manifest(skill_ids, metas)
        )

        cap = self._settings.skill_prompt_max_bytes
        if len(combined.encode("utf-8")) > cap:
            return EngineResponse(
                reply=f"技能正文合并后超出上限 ({cap // 1024}KB)，请精简正文或改用附件承载细节"
            )

        token = set_context(ctx)
        try:
            result = await AgentLoop(
                self._llm, self._tools, self._pending, self._audit,
                combined, allowed, self._settings.react_max_steps,
                observation_max_bytes=self._settings.react_observation_max_bytes,
                extra_preconditions=extra or None,
                observations=self._observations,
                budget=ctx.budget,
                stop_on_pending=True,
            ).run(message, history=history, on_progress=on_progress)
        except LLMError:
            return EngineResponse(reply="LLM 调用失败，技能暂不可用")
        finally:
            reset_context(token)
        return EngineResponse(
            reply=result.answer,
            data={
                "steps": [s.model_dump(mode="json") for s in result.steps],
                "stop_reason": result.stop_reason,
                "skill_ids": list(skill_ids),
                "skill_names": [m.effective_display_name for m in metas],
            },
            pending_actions=result.pending_actions,
        )

    def _resolve_creation_fallback(self, skill_ids: list[str], message: str) -> list[str]:
        """Route create-from-scratch PPT requests away from editor-only skill bundles.

        Some imported PPTX skills describe a shell-based authoring workflow but ship only
        editing/QA helpers. Maestro intentionally cannot execute model-authored shell/code,
        so use an installed trusted PPT generator when one is available.
        """
        if len(skill_ids) != 1 or skill_ids[0] != "pptx" or not _CREATE_PPT_RE.search(message):
            return skill_ids
        primary = self._store.get("pptx")
        if primary is None or self._generation_scripts(primary):
            return skill_ids
        candidates = [
            meta
            for meta in self._store.list_all()
            if meta.name != "pptx"
            and meta.user_invocable
            and not meta.disable_model_invocation
            and "ppt" in f"{meta.name} {meta.description}".lower()
            and self._generation_scripts(meta)
            and self._store.is_trusted(meta.name, meta.package_sha256)
        ]
        if not candidates:
            return skill_ids
        candidates.sort(key=lambda meta: (meta.name != "ppt-generator", meta.name))
        return [candidates[0].name]

    @staticmethod
    def _generation_scripts(meta) -> list[str]:
        return [
            script
            for script in meta.scripts
            if Path(script).suffix.lower() in _EXECUTABLE_SUFFIXES
            and Path(script).stem.lower().startswith(("generate", "create"))
        ]

    @staticmethod
    def _script_manifest(skill_ids: list[str], metas: list) -> str:
        entries = []
        multi_skill = len(skill_ids) > 1
        for sid, meta in zip(skill_ids, metas):
            scripts = [
                f"{sid}/{script}" if multi_skill else script
                for script in meta.scripts
                if Path(script).suffix.lower() in _EXECUTABLE_SUFFIXES
            ]
            if scripts:
                entries.append(f"- {sid}: {json.dumps(scripts, ensure_ascii=False)}")
        if not entries:
            return ""
        return (
            "\n\n---\n\n可执行脚本硬约束：`run_skill_script.script` 必须逐字使用以下清单中的路径；"
            "不得传入代码、shell 命令、`node -e` 或 `python -c`。参数放在 `args` 字符串数组中。\n"
            + "\n".join(entries)
        )

    def _file_manifest(self, skill_ids: list[str], metas: list) -> str:
        """把当前技能的附件路径以结构化 (JSON 转义) 形式注入正文，让 agent 无需先
        调 list_skill_files 就知道有哪些文件可读。路径来自技能包，按不可信文本转义。"""
        lines = []
        multi_skill = len(skill_ids) > 1
        for sid, m in zip(skill_ids, metas):
            paths = [
                a["path"] if not multi_skill else f"{sid}/{a['path']}"
                for a in self._store.list_attachments(sid)
            ]
            if paths:
                lines.append(
                    f"- 技能「{m.effective_display_name}」附带文件: "
                    f"{json.dumps(paths, ensure_ascii=False)}"
                )
        if not lines:
            return ""
        return (
            "\n\n---\n\n以下附件可用 `read_skill_file(path)` 按需读取"
            "（多技能执行时 path 为 `skill_id/相对路径`；`list_skill_files()` 亦可列出）:\n"
            + "\n".join(lines)
        )
