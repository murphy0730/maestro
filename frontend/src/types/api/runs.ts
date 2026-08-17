export type RunPath = 'unselected' | 'fast' | 'structured';
export type RunStatus =
  | 'created'
  | 'running_fast'
  | 'structuring'
  | 'running_structured'
  | 'waiting_approval'
  | 'waiting_external'
  | 'reconciling'
  | 'cancelling'
  | 'cancelled'
  | 'failed'
  | 'completed';
export type StepStatus =
  | 'pending'
  | 'ready'
  | 'waiting_approval'
  | 'running'
  | 'waiting_external'
  | 'reconciling'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'skipped';

export interface RunStep {
  step_id: string;
  /** 能力注册名（`StepRecord.kind` = `CapabilitySpec.name`），交给 `describeCapability` 翻译。 */
  kind: string;
  status: StepStatus;
  output_ref?: string | null;
  error_message?: string | null;
  /**
   * 以下字段 `GET /runs/{id}` 的快照里就有，SSE 事件里没有 —— 只读能力不建
   * `StepRecord`，所以事件推导出来的步骤只有上面那几项。
   */
  call?: { name?: string; arguments?: Record<string, unknown> } | null;
  error_kind?: string | null;
  attempt?: number;
}
export interface ApprovalView {
  approval_id: string;
  step_id: string;
  tool_id?: string;
  impact_summary: string;
  policy_reason: string;
  run_revision: number;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  expires_at?: string;
  /** `require_reconfirmation` 要求多次确认；已收集次数与所需次数。 */
  confirmations?: string[];
  confirmations_required?: number;
}
export interface RunSnapshot {
  run_id: string;
  session_id: string;
  objective: string;
  path: RunPath;
  status: RunStatus;
  steps: Record<string, RunStep>;
  pending_approvals: ApprovalView[];
  pending_approval_id?: string | null;
  requested_skills?: string[];
  final_text?: string | null;
  revision: number;
  intent?: { requested_skills?: string[]; source?: 'chat' | 'expert' | 'event' | 'resume' } | null;
  created_at?: string;
  updated_at?: string;
  input_artifact_ids?: string[];
}
export interface CreateRunRequest {
  session_id: string;
  message: string;
  source?: 'chat' | 'expert' | 'event' | 'resume';
  requested_skills?: string[];
  artifact_ids?: string[];
}
export interface ArtifactUpload {
  artifact_id: string;
  sha256: string;
  media_type: string;
  bytes: number;
}
export type PublicRunEventName =
  | 'run.created'
  | 'run.path_selected'
  | 'run.controlled_started'
  | 'run.path_upgraded'
  | 'run.waiting_approval'
  | 'run.waiting_external'
  | 'run.reconciling'
  | 'run.cancelling'
  | 'run.completed'
  | 'run.failed'
  | 'run.cancelled'
  | 'step.started'
  | 'step.succeeded'
  | 'step.failed'
  | 'approval.requested'
  | 'approval.expired'
  | 'approval.resolved'
  | 'artifact.created'
  | 'token.delta';
type Event<T extends PublicRunEventName, D extends Record<string, unknown>> = {
  event_id?: string;
  type: T;
  data: D;
  event_type?: AgentEventType | string;
  payload?: Record<string, unknown>;
  references?: Record<string, unknown>;
};
export type RunEvent =
  | Event<'run.created', Partial<RunSnapshot>>
  | Event<'run.path_selected', { path: RunPath }>
  | Event<'run.controlled_started', Record<string, unknown>>
  | Event<'run.path_upgraded', { from?: RunPath; to: 'structured'; reason?: string }>
  | Event<
      | 'run.waiting_approval'
      | 'run.waiting_external'
      | 'run.reconciling'
      | 'run.cancelling'
      | 'artifact.created',
      Record<string, unknown>
    >
  | Event<
      'run.completed' | 'run.failed' | 'run.cancelled',
      { final_text?: string; reason?: string; error_message?: string }
    >
  | Event<
      'step.started' | 'step.succeeded' | 'step.failed',
      {
        step_id?: string;
        capability_id?: string;
        name?: string;
        kind?: string;
        status?: string;
        error_message?: string;
      }
    >
  | Event<'approval.requested', Partial<ApprovalView>>
  | Event<
      'approval.expired' | 'approval.resolved',
      { approval_id?: string; status?: ApprovalView['status'] }
    >
  | Event<'token.delta', { delta?: string }>;
export interface UnknownRunEvent {
  event_id?: string;
  type: string;
  data: Record<string, unknown>;
  unknown: true;
}

export type AgentEventType =
  | 'USER_MESSAGE'
  | 'ASSISTANT_MESSAGE'
  | 'MESSAGE_REDACTED'
  | 'RUN_CREATED'
  | 'RUN_STATUS_CHANGED'
  | 'MODEL_TURN'
  | 'TOOL_SEARCH'
  | 'TOOL_CALL'
  | 'TOOL_RESULT'
  | 'SKILL_ACTIVATED'
  | 'PLAN_CREATED'
  | 'PLAN_STEP_UPDATED'
  | 'CONSTRAINT_ADDED'
  | 'CONSTRAINT_REMOVED'
  | 'DECISION_UPDATED'
  | 'EVIDENCE_RECALLED'
  | 'EVIDENCE_USED'
  | 'APPROVAL_REQUESTED'
  | 'APPROVAL_RESOLVED'
  | 'CHECKPOINT_CREATED'
  | 'CONTEXT_BUILT'
  | 'ARTIFACT_CREATED'
  | 'ERROR';

/** Durable v2 event. Optional legacy fields keep old persisted mock traces readable. */
export interface AgentEvent {
  event_id?: string;
  session_id?: string;
  run_id?: string | null;
  sequence?: number;
  event_type?: AgentEventType | string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  references?: Record<string, unknown>;
  created_at?: string;
  type?: string;
  data?: Record<string, unknown>;
  unknown?: boolean;
}
