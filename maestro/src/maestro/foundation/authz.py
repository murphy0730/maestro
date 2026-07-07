"""权限与动作分级 + 待确认动作管理。

所有写操作必须经 `ActionGate.request` 提交:
- `auto`: 立即执行并审计
- `requires_confirmation`: 生成 PendingAction 返回给用户，确认后经
  `ActionGate.confirm` 执行
- `deny`: 拒绝

策略用配置表驱动，方便调整。初始版本单用户，多用户体系留接口 (actor 参数)。
"""

import logging
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel

from maestro.domain.models import ActionResult, PendingAction
from maestro.foundation.audit import AuditLog

logger = logging.getLogger(__name__)

ActionLevel = Literal["auto", "requires_confirmation", "deny"]

# 授权策略配置表 (action_type → 级别)，未知写操作默认需确认 (保守)
DEFAULT_POLICIES: dict[str, ActionLevel] = {
    "send_expedite_message.internal": "auto",
    "send_expedite_message.supplier": "requires_confirmation",
    "dispatch_work_order": "requires_confirmation",
    "update_work_order_status": "requires_confirmation",
    "send_notification": "requires_confirmation",
}

Executor = Callable[[], Awaitable[ActionResult]]


class AuthZ:
    """动作分级授权策略 (读操作不经此层，始终允许)。"""

    def __init__(self, policies: dict[str, ActionLevel] | None = None):
        self.policies: dict[str, ActionLevel] = {**DEFAULT_POLICIES, **(policies or {})}

    def decide(self, action_type: str) -> ActionLevel:
        return self.policies.get(action_type, "requires_confirmation")


class PendingActionStore:
    """待确认动作存储 (内存)。保存动作元数据 + 延迟执行的 executor。"""

    def __init__(self):
        self._store: dict[str, tuple[PendingAction, Executor]] = {}

    def add(self, action: PendingAction, executor: Executor) -> None:
        self._store[action.action_id] = (action, executor)

    def get(self, action_id: str) -> PendingAction | None:
        item = self._store.get(action_id)
        return item[0] if item else None

    def list_pending(self) -> list[PendingAction]:
        return [a for a, _ in self._store.values() if a.status == "pending"]

    async def resolve(self, action_id: str, approved: bool) -> tuple[PendingAction, ActionResult | None]:
        item = self._store.get(action_id)
        if item is None:
            raise KeyError(f"待确认动作 {action_id} 不存在")
        action, executor = item
        if action.status != "pending":
            raise ValueError(f"动作 {action_id} 当前状态为 {action.status}，不可重复处理")
        if not approved:
            action.status = "rejected"
            return action, None
        try:
            result = await executor()
            action.status = "executed" if result.success else "failed"
        except Exception as e:  # noqa: BLE001 — 执行失败记录而非崩溃
            action.status = "failed"
            result = ActionResult(success=False, action=action.action_type, detail=str(e))
        return action, result


class GateOutcome(BaseModel):
    status: Literal["executed", "pending", "denied"]
    action: PendingAction | None = None
    result: ActionResult | None = None


class ActionGate:
    """写操作统一闸口: AuthZ 判级 → 执行/挂起/拒绝 → 审计。"""

    def __init__(self, authz: AuthZ, pending: PendingActionStore, audit: AuditLog):
        self.authz = authz
        self.pending = pending
        self.audit = audit

    async def request(
        self,
        action_type: str,
        description: str,
        params: dict | None = None,
        executor: Executor | None = None,
        actor: str = "system",
    ) -> GateOutcome:
        params = params or {}
        level = self.authz.decide(action_type)
        if level == "deny":
            self.audit.record(actor, action_type, params, "deny", {"status": "denied"})
            return GateOutcome(status="denied")
        if level == "auto":
            assert executor is not None
            try:
                result = await executor()
            except Exception as e:  # noqa: BLE001
                result = ActionResult(success=False, action=action_type, detail=str(e))
            self.audit.record(actor, action_type, params, "auto", result.model_dump())
            return GateOutcome(status="executed", result=result)
        # requires_confirmation: 不直接执行，挂起等待人确认
        action = PendingAction(action_type=action_type, description=description, params=params)
        assert executor is not None
        self.pending.add(action, executor)
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
        action, result = await self.pending.resolve(action_id, approved)
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
