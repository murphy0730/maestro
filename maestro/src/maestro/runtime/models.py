from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


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
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    pending_approvals: list[ApprovalRecord] = Field(default_factory=list)
    capability_versions: dict[str, str] = Field(default_factory=dict)
    consumed_steps: int = 0
    requires_reconciliation: bool = False
    final_text: str | None = None
    revision: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChildRunResult(BaseModel):
    """The bounded information a parent can receive from an isolated child run."""

    child_run_id: str
    status: RunStatus
    artifact_ref: str
