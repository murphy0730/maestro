"""Domain-neutral session trajectory and accumulated-state models.

The event stream is the durable fact log.  Checkpoints, plans, run snapshots and
status bars are projections derived from it; none of them replace the events
that produced them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from maestro.runtime.models import RunPath, RunStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentEventType(StrEnum):
    USER_MESSAGE = "USER_MESSAGE"
    ASSISTANT_MESSAGE = "ASSISTANT_MESSAGE"
    MESSAGE_REDACTED = "MESSAGE_REDACTED"
    RUN_CREATED = "RUN_CREATED"
    RUN_STATUS_CHANGED = "RUN_STATUS_CHANGED"
    MODEL_TURN = "MODEL_TURN"
    TOOL_SEARCH = "TOOL_SEARCH"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    SKILL_ACTIVATED = "SKILL_ACTIVATED"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_STEP_UPDATED = "PLAN_STEP_UPDATED"
    CONSTRAINT_ADDED = "CONSTRAINT_ADDED"
    CONSTRAINT_REMOVED = "CONSTRAINT_REMOVED"
    DECISION_UPDATED = "DECISION_UPDATED"
    EVIDENCE_RECALLED = "EVIDENCE_RECALLED"
    EVIDENCE_USED = "EVIDENCE_USED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    CONTEXT_BUILT = "CONTEXT_BUILT"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    ERROR = "ERROR"


class AgentSession(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "新对话"
    agent_id: str
    agent_definition_version: str
    prefix_text: str
    prefix_hash: str
    capability_index_hash: str
    model_profile_id: str
    status: Literal["active", "archived"] = "active"
    active_run_id: str | None = None
    next_event_sequence: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    parent_run_id: str | None = None
    objective: str
    path: RunPath = RunPath.UNSELECTED
    status: RunStatus = RunStatus.CREATED
    principal_id: str = "local-user"
    requested_skills: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    active_skill_versions: dict[str, str] = Field(default_factory=dict)
    active_tool_versions: dict[str, str] = Field(default_factory=dict)
    consumed_steps: int = 0
    max_steps: int = Field(default=24, ge=1, le=100)
    max_seconds: int = Field(default=600, ge=1, le=86400)
    revision: int = 0
    current_plan_id: str | None = None
    pending_approval_id: str | None = None
    final_text: str | None = None
    error_code: str | None = None
    working_state: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    event_type: AgentEventType
    payload: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    references: dict[str, object] = Field(default_factory=dict)
    token_count: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class SourceRef(BaseModel):
    source_type: str
    source_ref: str
    evidence_id: str | None = None


class ConstraintState(BaseModel):
    constraint_id: str
    value: str
    source_ref: str
    scope: str = "session"


class DecisionState(BaseModel):
    decision_id: str
    value: str
    source_ref: str
    supersedes: str | None = None


class FactState(BaseModel):
    fact_id: str
    value: str
    source: SourceRef
    validity: Literal["stable", "volatile"] = "stable"
    observed_at: datetime | None = None
    refresh_after: datetime | None = None

    @model_validator(mode="after")
    def volatile_facts_are_timestamped(self) -> "FactState":
        if self.validity == "volatile" and self.observed_at is None:
            raise ValueError("volatile facts require observed_at")
        return self


class ActiveSkillState(BaseModel):
    skill_id: str
    version: str
    phase: str = "active"


class PlanMilestones(BaseModel):
    plan_id: str | None = None
    current_phase: str = ""
    completed: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)


class CheckpointState(BaseModel):
    primary_goal: str = ""
    goal_source_ref: str | None = None
    constraints: list[ConstraintState] = Field(default_factory=list)
    decisions: list[DecisionState] = Field(default_factory=list)
    current_state: dict[str, object] = Field(default_factory=dict)
    facts: list[FactState] = Field(default_factory=list)
    completed_actions: list[str] = Field(default_factory=list)
    pending_actions: list[str] = Field(default_factory=list)
    active_skills: list[ActiveSkillState] = Field(default_factory=list)
    plan: PlanMilestones = Field(default_factory=PlanMilestones)
    confirmations: dict[str, bool] = Field(default_factory=dict)


class CheckpointRecord(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    parent_checkpoint_id: str | None = None
    generation: int = Field(ge=1)
    covered_until_sequence: int = Field(ge=0)
    state: CheckpointState
    token_count: int | None = Field(default=None, ge=0)
    build_type: Literal["incremental", "force", "full_rebase"]
    created_at: datetime = Field(default_factory=utc_now)


class StateDelta(BaseModel):
    goal: str | None = None
    goal_source_ref: str | None = None
    constraints_added: list[ConstraintState] = Field(default_factory=list)
    constraint_ids_removed: list[str] = Field(default_factory=list)
    decisions_added: list[DecisionState] = Field(default_factory=list)
    decision_ids_superseded: list[str] = Field(default_factory=list)
    state_changes: dict[str, object] = Field(default_factory=dict)
    facts_added: list[FactState] = Field(default_factory=list)
    fact_ids_invalidated: list[str] = Field(default_factory=list)
    actions_completed: list[str] = Field(default_factory=list)
    actions_pending: list[str] = Field(default_factory=list)
    active_skills: list[ActiveSkillState] = Field(default_factory=list)
    confirmations: dict[str, bool] = Field(default_factory=dict)


class PlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanTaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanRecord(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str
    goal: str
    status: PlanStatus = PlanStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PlanTaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    plan_id: str
    parent_task_id: str | None = None
    title: str
    description: str = ""
    status: PlanTaskStatus = PlanTaskStatus.PENDING
    priority: int = 0
    sequence: int = Field(ge=0)
    depends_on: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str | None = None
    source_type: str
    source_ref: str
    content_digest: str
    validity: Literal["stable", "volatile"] = "stable"
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    recall_event_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceUsage(BaseModel):
    usage_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str | None = None
    evidence_id: str
    derived_fact: str
    usage_type: Literal["answer", "decision", "constraint", "tool_call", "state_update"]
    future_relevant: bool = False
    event_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalState(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    session_id: str
    tool_id: str
    tool_version: str
    schema_hash: str
    arguments: dict[str, object]
    arguments_hash: str
    idempotency_key: str
    impact_summary: str
    policy_reason: str
    external_state_token: str | None = None
    run_revision: int
    run_allowed_tools: list[str] | None = None
    skill_allowed_tools: list[str] | None = None
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    confirmations_required: int = 1
    confirmations: list[str] = Field(default_factory=list)
    expires_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class ContextManifest(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    run_id: str
    checkpoint_id: str | None = None
    first_event_sequence: int | None = None
    last_event_sequence: int | None = None
    prefix_hash: str
    model_profile_id: str
    tool_versions: dict[str, str] = Field(default_factory=dict)
    skill_versions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    token_breakdown: dict[str, int] = Field(default_factory=dict)
    estimated_prompt_tokens: int = 0
    actual_usage: dict[str, int] = Field(default_factory=dict)
    context_hash: str
    created_at: datetime = Field(default_factory=utc_now)
