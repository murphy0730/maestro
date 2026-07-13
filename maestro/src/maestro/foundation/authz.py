"""权限与动作分级 + 待确认动作管理。

所有写操作必须经 `ActionGate.request` 提交:
- `auto`: 立即执行并审计
- `requires_confirmation`: 生成 PendingAction 返回给用户，确认后经
  `ActionGate.confirm` 执行
- `deny`: 拒绝

策略用配置表驱动，方便调整。初始版本单用户，多用户体系留接口 (actor 参数)。
"""

import asyncio
import hashlib
import json as _json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel

from maestro.domain.models import ActionResult, PendingAction
from maestro.foundation.audit import AuditLog
from maestro.foundation.exec_context import ExecMode, current_mode
from maestro.foundation.permissions import (
    ActionLevel,
    PermissionEngine,
    effect_to_level,
)

logger = logging.getLogger(__name__)

Executor = Callable[[], Awaitable[ActionResult]]
ParamExecutor = Callable[[dict], Awaitable[ActionResult]]
Revalidator = Callable[[dict], Awaitable[tuple[bool, str]]]


class AuthZ:
    """动作分级授权策略 (读操作不经此层，始终允许)。

    v0.3: 判级不再硬编码，转为委托统一权限引擎 (PermissionEngine)。可传入共享
    engine (与 ReAct 的 can_use_tool 层同源)；未传则按 policies 自建一个。
    """

    def __init__(
        self,
        policies: dict[str, ActionLevel] | None = None,
        engine: PermissionEngine | None = None,
    ):
        self.engine = engine or PermissionEngine(action_policies=policies)

    def decide(self, action_type: str, mode: ExecMode = "plan") -> ActionLevel:
        return effect_to_level(self.engine.evaluate_action(action_type, mode).effect)


# 进入去重指纹的结构化业务键；note/content/description 等自由文本每次措辞不同，
# 纳入会使指纹失效，故排除。无任何业务键的动作不参与去重 (避免不同意图被误合)。
_FINGERPRINT_KEYS = (
    "wo_id", "material_id", "line_id", "recipient", "channel",
    "status", "skill_id", "script", "file_path",
)


def action_fingerprint(action_type: str, params: dict) -> str | None:
    """同一事实的写动作指纹: action_type + 结构化业务键。无业务键 → None (不去重)。"""
    keys = {k: params[k] for k in _FINGERPRINT_KEYS if params.get(k) is not None}
    if not keys:
        return None
    payload = _json.dumps(
        {"type": action_type, **keys}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class PendingActionStore:
    """待确认动作存储。测试可纯内存，运行时可用 SQLite 恢复结构化动作。"""

    def __init__(self, db_path: Path | None = None):
        self._store: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()
        self._db_path = db_path
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS pending_actions "
                    "(action_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                rows = db.execute("SELECT payload FROM pending_actions").fetchall()
            for (payload,) in rows:
                action = PendingAction.model_validate_json(payload)
                if action.status == "executing":
                    action.status = "failed"
                    action.failure_reason = "服务在动作执行期间中断，请重新发起"
                    action.resolved_at = datetime.now()
                    self._save(action)
                self._store[action.action_id] = action

    def _save(self, action: PendingAction) -> None:
        if self._db_path is None:
            return
        with sqlite3.connect(self._db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO pending_actions(action_id, payload) VALUES (?, ?)",
                (action.action_id, action.model_dump_json()),
            )

    def add(self, action: PendingAction) -> None:
        self._store[action.action_id] = action
        self._save(action)

    def find_pending_by_fingerprint(self, fingerprint: str) -> PendingAction | None:
        for action in self._store.values():
            if action.status == "pending" and action.fingerprint == fingerprint:
                return action
        return None

    def get(self, action_id: str) -> PendingAction | None:
        return self._store.get(action_id)

    def list_pending(self) -> list[PendingAction]:
        return [action for action in self._store.values() if action.status == "pending"]

    async def claim(self, action_id: str, approved: bool) -> PendingAction:
        """原子领取动作，防止两个确认请求重复执行同一副作用。"""
        async with self._lock:
            item = self._store.get(action_id)
            if item is None:
                raise KeyError(f"待确认动作 {action_id} 不存在")
            action = item
            if action.status != "pending":
                raise ValueError(f"动作 {action_id} 当前状态为 {action.status}，不可重复处理")
            action.resolved_at = datetime.now() if not approved else None
            action.status = "executing" if approved else "rejected"
            action.started_at = datetime.now() if approved else None
            self._save(action)
            return action

    async def execute_claimed(
        self, action_id: str, executor: ParamExecutor
    ) -> tuple[PendingAction, ActionResult]:
        action = self._store[action_id]
        try:
            result = await executor(action.params)
            action.status = "executed" if result.success else "failed"
        except Exception as e:  # noqa: BLE001 — 执行失败记录而非崩溃
            action.status = "failed"
            result = ActionResult(success=False, action=action.action_type, detail=str(e))
        action.resolved_at = datetime.now()
        action.failure_reason = None if result.success else result.detail
        self._save(action)
        return action, result

    def finish_without_execution(self, action_id: str, status: str, reason: str) -> PendingAction:
        action = self._store[action_id]
        action.status = status
        action.failure_reason = reason
        action.resolved_at = datetime.now()
        self._save(action)
        return action


class GateOutcome(BaseModel):
    status: Literal["executed", "pending", "denied"]
    action: PendingAction | None = None
    result: ActionResult | None = None


class ActionGate:
    """写操作统一闸口: AuthZ 判级 → 执行/挂起/拒绝 → 审计。"""

    def __init__(
        self,
        authz: AuthZ,
        pending: PendingActionStore,
        audit: AuditLog,
        revalidation_seconds: int = 300,
        expiration_seconds: int = 86400,
    ):
        self.authz = authz
        self.pending = pending
        self.audit = audit
        self.revalidation_seconds = revalidation_seconds
        self.expiration_seconds = expiration_seconds
        self._revalidators: dict[str, Revalidator] = {}
        self._executors: dict[str, ParamExecutor] = {}
        self._ephemeral_executors: dict[str, Executor] = {}

    def register_revalidator(self, action_type: str, revalidator: Revalidator) -> None:
        self._revalidators[action_type] = revalidator

    def register_executor(self, action_type: str, executor: ParamExecutor) -> None:
        self._executors[action_type] = executor

    async def request(
        self,
        action_type: str,
        description: str,
        params: dict | None = None,
        executor: Executor | None = None,
        actor: str = "system",
        min_level: ActionLevel | None = None,
    ) -> GateOutcome:
        params = params or {}
        # 执行模式由 Orchestrator.handle 经 contextvar 注入; 事件驱动/CLI 取默认 "plan"
        level = self.authz.decide(action_type, current_mode())
        # 调用方可抬高最低门级 (如命令级风险判定为 ask 时强制 requires_confirmation)，
        # 使确认要求不依赖按工具名维护的策略表。
        if min_level is not None:
            order = {"auto": 0, "requires_confirmation": 1, "deny": 2}
            if order[min_level] > order[level]:
                level = min_level
        if level == "deny":
            self.audit.record(actor, action_type, params, "deny", {"status": "denied"})
            return GateOutcome(status="denied")
        if level == "auto":
            registered = self._executors.get(action_type)
            if executor is None and registered is None:
                raise RuntimeError(f"动作 {action_type} 未注册执行器")
            try:
                result = await executor() if executor is not None else await registered(params)
            except Exception as e:  # noqa: BLE001
                result = ActionResult(success=False, action=action_type, detail=str(e))
            self.audit.record(actor, action_type, params, "auto", result.model_dump())
            return GateOutcome(status="executed", result=result)
        # requires_confirmation: 不直接执行，挂起等待人确认。
        # 同指纹 (同事实) 已有未过期 pending 时复用它，防止巡检/事件反复唤醒
        # 把相同的跟踪/通知动作灌爆确认队列。
        fingerprint = action_fingerprint(action_type, params)
        if fingerprint is not None:
            existing = self.pending.find_pending_by_fingerprint(fingerprint)
            if existing is not None and datetime.now() - existing.created_at < timedelta(
                seconds=self.expiration_seconds
            ):
                self.audit.record(
                    actor,
                    action_type,
                    params,
                    "requires_confirmation",
                    {"status": "dedup_hit", "action_id": existing.action_id},
                )
                return GateOutcome(status="pending", action=existing)
        action = PendingAction(
            action_type=action_type, description=description, params=params,
            fingerprint=fingerprint,
        )
        if executor is None and action_type not in self._executors:
            raise RuntimeError(f"动作 {action_type} 未注册执行器")
        if executor is not None:
            self._ephemeral_executors[action.action_id] = executor
        self.pending.add(action)
        self.audit.record(
            actor,
            action_type,
            params,
            "requires_confirmation",
            {"status": "pending", "action_id": action.action_id},
        )
        return GateOutcome(status="pending", action=action)

    async def confirm(
        self, action_id: str, approved: bool, actor: str = "user"
    ) -> tuple[PendingAction, ActionResult | None]:
        action = await self.pending.claim(action_id, approved)
        # 无论批准/拒绝/过期都释放临时闭包, 否则未批准的动作会永久驻留 (内存泄漏)。
        ephemeral = self._ephemeral_executors.pop(action_id, None)
        result = None
        if approved:
            registered = self._executors.get(action.action_type)
            executor = registered or (
                (lambda _params: ephemeral()) if ephemeral is not None else None
            )
            if executor is None:
                action = self.pending.finish_without_execution(
                    action_id, "failed", "动作执行器不可用，请重新发起"
                )
                self.audit.record(
                    actor, f"confirm:{action.action_type}",
                    {"action_id": action_id, "approved": approved},
                    "requires_confirmation", {"status": action.status},
                )
                return action, None
            age = (datetime.now() - action.validated_at).total_seconds()
            if age >= self.expiration_seconds:
                action = self.pending.finish_without_execution(
                    action_id, "expired", "待确认动作已过期，请重新发起"
                )
            elif age >= self.revalidation_seconds:
                decision = self.authz.decide(action.action_type, "plan")
                if decision == "deny":
                    action = self.pending.finish_without_execution(
                        action_id, "validation_failed", "当前权限策略已拒绝该动作"
                    )
                else:
                    revalidator = self._revalidators.get(action.action_type)
                    ok, reason = await revalidator(action.params) if revalidator else (True, "")
                    if not ok:
                        action = self.pending.finish_without_execution(
                            action_id, "validation_failed", reason
                        )
                    else:
                        action.validated_at = datetime.now()
                        action, result = await self.pending.execute_claimed(action_id, executor)
            else:
                action, result = await self.pending.execute_claimed(action_id, executor)
        self.audit.record(
            actor,
            f"confirm:{action.action_type}",
            {"action_id": action_id, "approved": approved},
            "requires_confirmation",
            result.model_dump() if result else {"status": action.status},
        )
        return action, result


def gate_outcome_summary(outcome: GateOutcome) -> str:
    """人类可读的闸口结果摘要 (用于回复文本)。"""
    if outcome.status == "executed":
        detail = outcome.result.detail if outcome.result else ""
        return f"已自动执行: {detail}"
    if outcome.status == "pending":
        assert outcome.action is not None
        return f"待确认 [{outcome.action.action_id}]: {outcome.action.description}"
    return "已被权限策略拒绝"
