import json
import logging
from typing import Awaitable, Callable

from maestro.engines.base import ProgressFn, emit_progress
from maestro.engines.scheduling.run_state import RunState
from maestro.foundation.audit import AuditLog
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.permissions import PermissionDecision, PermissionEngine
from maestro.foundation.tools.registry import Precondition, Tool, ToolProgress, ToolRegistry
from maestro.foundation.tools.validation import validate_arguments

logger = logging.getLogger(__name__)

ConfirmResolver = Callable[[str, dict, PermissionDecision], Awaitable[bool | None]]


class ToolExecutor:
    def __init__(
        self,
        tools: ToolRegistry,
        audit: AuditLog,
        allowed_tools: list[str],
        observation_max_bytes: int,
        extra_preconditions: dict[str, list[Precondition]] | None = None,
        permissions: PermissionEngine | None = None,
        confirm_resolver: ConfirmResolver | None = None,
        validate_input: bool = True,
        observations: ObservationStore | None = None,
    ):
        self._tools = tools
        self._audit = audit
        self._allowed = set(allowed_tools)
        self._obs_max = observation_max_bytes
        self._extra = extra_preconditions
        self._permissions = permissions
        self._confirm = confirm_resolver
        self._validate_input = validate_input
        self._observations = observations

    def parallelizable(self, name: str) -> bool:
        if name not in self._allowed:
            return False
        try:
            return self._tools.get(name).kind in ("read", "aux")
        except KeyError:
            return False

    async def handle_call(
        self,
        name: str,
        args: dict,
        state: RunState,
        on_progress: ProgressFn | None = None,
    ) -> tuple[object, bool]:
        observation, tool = await self.gate_call(name, args, state)
        if tool is None:
            return observation, True
        return await self.execute_call(tool, name, args, state, on_progress)

    async def gate_call(
        self, name: str, args: dict, state: RunState
    ) -> tuple[object | None, Tool | None]:
        if name not in self._allowed:
            return {"blocked": f"工具 {name} 不在调度引擎白名单内，已拒绝"}, None

        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        state.seen[key] = state.seen.get(key, 0) + 1
        if state.seen[key] > 1:
            return {
                "blocked": "重复的相同工具调用，已跳过 (疑似绕圈)。请基于已有观察给出结论或改换思路。"
            }, None

        tool = self._tools.get(name)
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
                if approved is None:
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
                if not approved:
                    return {"blocked": f"用户拒绝执行 {name}"}, None

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

        if self._extra is not None:
            for precondition in self._extra.get(name, []):
                result = await precondition(args)
                if not result.ok:
                    self._audit.record(
                        actor="scheduling_agent",
                        action=f"skill_precondition_blocked:{name}",
                        params=args,
                        result={"reason": result.reason},
                    )
                    return {"blocked": f"技能前置断言未通过: {result.reason}"}, None

        return None, tool

    async def execute_call(
        self,
        tool: Tool,
        name: str,
        args: dict,
        state: RunState,
        on_progress: ProgressFn | None = None,
    ) -> tuple[object, bool]:
        try:
            result = await self._tools.execute(
                name, args, on_progress=self.tool_progress(on_progress, name)
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("[AGENT] 工具 %s 执行失败: %s", name, error)
            return {"error": str(error)}, False
        if tool.kind == "write":
            state.seen = {
                key: count
                for key, count in state.seen.items()
                if self._tools.get(key[0]).kind == "write"
            }
        return result, False

    def serialize_observation(self, observation: object) -> tuple[str, object]:
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

    def tool_progress(self, on_progress: ProgressFn | None, name: str) -> ToolProgress | None:
        if on_progress is None:
            return None

        async def callback(event: dict) -> None:
            label = f"{name} {event.get('phase', '')}".strip()
            percent = event.get("percent")
            if percent is not None:
                label += f" {percent}%"
            message = event.get("message")
            if message:
                label += f": {message}"
            await emit_progress(on_progress, label)

        return callback

    async def _ask_permission(
        self, name: str, args: dict, decision: PermissionDecision
    ) -> bool | None:
        if self._confirm is None:
            return None
        return await self._confirm(name, args, decision)
