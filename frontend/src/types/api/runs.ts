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

export interface RunStep { step_id: string; kind: string; status: StepStatus; output_ref?: string | null; error_message?: string | null }
export interface ApprovalView { approval_id: string; step_id: string; impact_summary: string; policy_reason: string; run_revision: number; status: 'pending' | 'approved' | 'rejected' | 'expired'; expires_at?: string }
export interface RunSnapshot {
  run_id: string; session_id: string; objective: string; path: RunPath; status: RunStatus;
  steps: Record<string, RunStep>; pending_approvals: ApprovalView[]; final_text?: string | null;
  revision: number; intent?: { requested_skills?: string[]; source?: 'chat' | 'expert' | 'event' | 'resume' } | null;
}
export interface CreateRunRequest { session_id: string; message: string; source?: 'chat' | 'expert' | 'event' | 'resume'; skill_names?: string[]; artifact_ids?: string[] }
export interface ArtifactUpload { artifact_id: string; sha256: string; media_type: string; bytes: number }
export type PublicRunEventName =
  | 'run.created' | 'run.path_selected' | 'run.path_upgraded' | 'run.waiting_approval'
  | 'run.reconciling' | 'run.completed' | 'run.failed' | 'run.cancelled'
  | 'step.started' | 'step.succeeded' | 'step.failed' | 'approval.requested'
  | 'approval.expired' | 'approval.resolved' | 'artifact.created' | 'token.delta';
type Event<T extends PublicRunEventName, D extends Record<string, unknown>> = { event_id?: string; type: T; data: D };
export type RunEvent =
  | Event<'run.created', Partial<RunSnapshot>>
  | Event<'run.path_selected', { path: RunPath }>
  | Event<'run.path_upgraded', { from?: RunPath; to: 'structured'; reason?: string }>
  | Event<'run.waiting_approval' | 'run.reconciling' | 'artifact.created', Record<string, unknown>>
  | Event<'run.completed' | 'run.failed' | 'run.cancelled', { final_text?: string }>
  | Event<'step.started' | 'step.succeeded' | 'step.failed', { step_id?: string; capability_id?: string; kind?: string; error_message?: string }>
  | Event<'approval.requested', Partial<ApprovalView>>
  | Event<'approval.expired' | 'approval.resolved', { approval_id?: string; status?: ApprovalView['status'] }>
  | Event<'token.delta', { delta?: string }>
  | { event_id?: string; type: string; data: Record<string, unknown> };
