import { create } from 'zustand';
import type { ApprovalView, RunEvent, RunPath, RunSnapshot, RunStatus, RunStep } from '@/types/api/runs';

export interface RunProjection {
  run: RunSnapshot | null;
  tokens: string;
  upgradeReason?: string;
  recovered: boolean;
  diagnostics: string[];
}
export const INITIAL_RUN_STATE: RunProjection = { run: null, tokens: '', diagnostics: [], recovered: false };

const terminal = new Set<RunStatus>(['completed', 'failed', 'cancelled']);
const statusFor = (type: string): RunStatus | undefined => ({ 'run.completed': 'completed', 'run.failed': 'failed', 'run.cancelled': 'cancelled', 'run.waiting_approval': 'waiting_approval', 'run.reconciling': 'reconciling' })[type] as RunStatus | undefined;
const stepStatus = (type: string): RunStep['status'] | undefined => ({ 'step.started': 'running', 'step.succeeded': 'succeeded', 'step.failed': 'failed' })[type] as RunStep['status'] | undefined;

export function reduceRunEvent(state: RunProjection, event: RunEvent): RunProjection {
  const data: Record<string, unknown> = event.data;
  if (event.type === 'run.created') {
    if (state.run) return state;
    const snapshot = data as unknown as Partial<RunSnapshot>;
    if (!snapshot.run_id || !snapshot.status || !snapshot.path) return { ...state, diagnostics: [...state.diagnostics, 'Received partial run.created event'] };
    return { ...state, run: { ...(snapshot as RunSnapshot), steps: snapshot.steps ?? {}, pending_approvals: snapshot.pending_approvals ?? [] }, recovered: snapshot.intent?.source === 'resume' };
  }
  if (!state.run) return { ...state, diagnostics: [...state.diagnostics, `Ignored ${event.type} before run.created`] };
  if (event.type === 'token.delta') return { ...state, tokens: state.tokens + String(data.delta ?? '') };
  if (event.type === 'run.path_selected') return { ...state, run: { ...state.run, path: data.path as RunPath } };
  if (event.type === 'run.path_upgraded') return { ...state, run: { ...state.run, path: 'structured', status: 'running_structured' }, upgradeReason: String(data.reason ?? '') };
  const newStepStatus = stepStatus(event.type);
  if (newStepStatus) {
    const stepId = String(data.step_id ?? data.capability_id ?? 'runtime');
    const previous = state.run.steps[stepId] ?? { step_id: stepId, kind: String(data.kind ?? 'capability'), status: 'pending' as const };
    return { ...state, run: { ...state.run, steps: { ...state.run.steps, [stepId]: { ...previous, status: newStepStatus, error_message: data.error_message as string | undefined } } } };
  }
  if (event.type === 'approval.requested') {
    if (!data.approval_id) return { ...state, diagnostics: [...state.diagnostics, 'Approval detail will be loaded from snapshot'] };
    const approval = data as unknown as ApprovalView;
    return { ...state, run: { ...state.run, status: 'waiting_approval', pending_approvals: [...state.run.pending_approvals.filter((item) => item.approval_id !== approval.approval_id), approval] } };
  }
  if (event.type === 'approval.resolved' || event.type === 'approval.expired') {
    const approvalId = String(data.approval_id ?? '');
    return { ...state, run: { ...state.run, pending_approvals: state.run.pending_approvals.map((item) => item.approval_id === approvalId ? { ...item, status: event.type === 'approval.expired' ? 'expired' : (data.status as ApprovalView['status'] ?? 'approved') } : item) } };
  }
  if (event.type === 'artifact.created') return state;
  const runStatus = statusFor(event.type);
  if (runStatus) return { ...state, run: { ...state.run, status: runStatus, final_text: terminal.has(runStatus) ? String(data.final_text ?? state.tokens) : state.run.final_text } };
  return { ...state, diagnostics: [...state.diagnostics, `Ignored unknown event ${event.type}`] };
}
export function reduceRunEvents(state: RunProjection, events: RunEvent[]) { return events.reduce(reduceRunEvent, state); }

function mergeSnapshot(state: RunProjection, snapshot: RunSnapshot | null): RunProjection {
  if (!snapshot) return { ...INITIAL_RUN_STATE, run: null };
  const current = state.run;
  return { ...state, run: { ...snapshot, steps: { ...(current?.steps ?? {}), ...(snapshot.steps ?? {}) } }, recovered: state.recovered || snapshot.intent?.source === 'resume' };
}
interface RunStore extends RunProjection { apply: (event: RunEvent) => void; diagnose: (message: string) => void; setRun: (run: RunSnapshot | null) => void; mergeRun: (run: RunSnapshot) => void; reset: () => void; }
export const useRunStore = create<RunStore>((set) => ({ ...INITIAL_RUN_STATE, apply: (event) => set((state) => reduceRunEvent(state, event)), diagnose: (message) => set((state) => ({ diagnostics: [...state.diagnostics, message] })), setRun: (run) => set({ ...INITIAL_RUN_STATE, run, recovered: run?.intent?.source === 'resume' }), mergeRun: (run) => set((state) => mergeSnapshot(state, run)), reset: () => set(INITIAL_RUN_STATE) }));
