from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class RunPath(StrEnum):
    UNSELECTED = "unselected"
    FAST = "fast"
    STRUCTURED = "structured"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING_FAST = "running_fast"
    STRUCTURING = "structuring"
    RUNNING_STRUCTURED = "running_structured"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_EXTERNAL = "waiting_external"
    RECONCILING = "reconciling"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


class StepStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    RECONCILING = "reconciling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RuntimeErrorKind(StrEnum):
    SCHEMA_INPUT = "schema_input"
    BUSINESS_BLOCKED = "business_blocked"
    AUTHORIZATION = "authorization"
    TRANSIENT_INFRASTRUCTURE = "transient_infrastructure"
    UNKNOWN_OR_BUG = "unknown_or_bug"


class RunIntent(BaseModel):
    objective: str = Field(min_length=1)
    source: Literal["chat", "expert", "event", "resume"] = "chat"
    principal_id: str = "local-user"
    requested_skills: list[str] = Field(default_factory=list)
    candidate_capabilities: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    complexity_signals: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=12, ge=1, le=100)
    max_seconds: int = Field(default=300, ge=1, le=86400)
    allow_background: bool = False
    path: RunPath = RunPath.UNSELECTED


class GoalSpec(BaseModel):
    objective: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(min_length=1)
    required_outputs: list[str] = Field(default_factory=list)
    known_inputs: dict[str, object] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    risk_context: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", frozen=True)
    kind: Literal["model", "skill", "tool", "mcp", "verify", "reconcile"]
    capability: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    input_refs: dict[str, str] = Field(default_factory=dict)
    output_key: str | None = None
    max_attempts: int = Field(default=1, ge=1, le=5)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    requires_approval: bool = False
    success_condition: str = Field(
        default="capability_succeeded", pattern=r"^[a-z][a-z0-9_]{0,63}$"
    )


class TypedPlan(BaseModel):
    goal: GoalSpec
    steps: list[PlanStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> "TypedPlan":
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step id")
        known = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"missing dependency: {sorted(missing)}")
            if step.step_id in step.depends_on:
                raise ValueError("step cannot depend on itself")
        return self


class ApprovalRecord(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid4()), frozen=True)
    run_id: str = Field(frozen=True)
    step_id: str = Field(frozen=True)
    call_sha256: str
    impact_summary: str
    policy_reason: str
    external_state_token: str | None = None
    run_revision: int
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    expires_at: datetime


class StepRecord(BaseModel):
    run_id: str = Field(frozen=True)
    step_id: str = Field(frozen=True)
    kind: str
    status: StepStatus = StepStatus.PENDING
    attempt: int = 0
    idempotency_key: str | None = None
    output_ref: str | None = None
    error_kind: RuntimeErrorKind | None = None
    error_message: str | None = None
    revision: int = 0


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()), frozen=True)
    parent_run_id: str | None = None
    session_id: str = "default"
    objective: str
    path: RunPath = RunPath.UNSELECTED
    status: RunStatus = RunStatus.CREATED
    intent: RunIntent | None = None
    goal_spec: GoalSpec | None = None
    typed_plan: TypedPlan | None = None
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    pending_approvals: list[ApprovalRecord] = Field(default_factory=list)
    capability_versions: dict[str, str] = Field(default_factory=dict)
    consumed_steps: int = 0
    requires_reconciliation: bool = False
    final_text: str | None = None
    revision: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
