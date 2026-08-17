"""Sparse runtime status projection and deterministic trajectory alerts."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.trajectory import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    CheckpointState,
    PlanTaskRecord,
    PlanTaskStatus,
)


class ExecutionGate(BaseModel):
    action: str
    status: str
    reason: str


class RuntimeStatusBar(BaseModel):
    goal: str = ""
    current_step: str = ""
    next_action: str = ""
    blockers: list[str] = Field(default_factory=list)
    critical_constraints: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    execution_gate: ExecutionGate | None = None

    def render(self) -> str:
        data = self.model_dump(mode="json", exclude_none=True)
        sparse = {
            key: value
            for key, value in data.items()
            if value not in ("", [], {}, None)
        }
        import json

        return "<agent_state>\n" + json.dumps(
            sparse, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n</agent_state>"


class TrajectoryMonitor:
    def alerts(self, events: list[AgentEvent]) -> list[str]:
        alerts: list[str] = []
        calls = [
            str(event.payload.get("normalized_call"))
            for event in events
            if event.event_type is AgentEventType.TOOL_CALL
            and event.payload.get("normalized_call")
        ]
        counts = Counter(calls)
        repeated = [call for call, count in counts.items() if count >= 2]
        if repeated:
            alerts.append("检测到相同 Tool 与参数重复调用。")

        progress_types = {
            AgentEventType.PLAN_STEP_UPDATED,
            AgentEventType.CONSTRAINT_ADDED,
            AgentEventType.CONSTRAINT_REMOVED,
            AgentEventType.DECISION_UPDATED,
            AgentEventType.EVIDENCE_USED,
            AgentEventType.APPROVAL_RESOLVED,
        }
        since_progress = 0
        for event in reversed(events):
            if event.event_type in progress_types:
                break
            if event.event_type in {AgentEventType.MODEL_TURN, AgentEventType.TOOL_RESULT}:
                since_progress += 1
        if since_progress >= 4:
            alerts.append(f"连续 {since_progress} 个步骤没有形成持久状态进展。")
        return alerts


class StatusBarBuilder:
    def __init__(self, store: SQLiteStore, monitor: TrajectoryMonitor | None = None) -> None:
        self._store = store
        self._monitor = monitor or TrajectoryMonitor()

    def build(
        self,
        run: AgentRun,
        checkpoint: CheckpointState,
        events: list[AgentEvent],
    ) -> RuntimeStatusBar:
        current: PlanTaskRecord | None = None
        following: PlanTaskRecord | None = None
        if run.current_plan_id:
            try:
                _, tasks = self._store.get_plan(run.current_plan_id)
            except FileNotFoundError:
                tasks = []
            current = next(
                (task for task in tasks if task.status is PlanTaskStatus.IN_PROGRESS), None
            )
            following = next(
                (
                    task
                    for task in tasks
                    if task.status in {PlanTaskStatus.READY, PlanTaskStatus.PENDING}
                    and task is not current
                ),
                None,
            )

        blockers = [
            f"事实已过期：{fact.value}"
            for fact in checkpoint.facts
            if fact.validity == "volatile"
            and fact.refresh_after is not None
            and fact.refresh_after <= datetime.now(UTC)
        ]
        gate = None
        if run.pending_approval_id:
            gate = ExecutionGate(
                action="pending_write",
                status="blocked",
                reason="user_confirmation_missing",
            )
        return RuntimeStatusBar(
            goal=checkpoint.primary_goal or run.objective,
            current_step=current.title if current else "",
            next_action=following.title if following else "",
            blockers=blockers,
            critical_constraints=[item.value for item in checkpoint.constraints[:3]],
            alerts=self._monitor.alerts(events),
            execution_gate=gate,
        )
