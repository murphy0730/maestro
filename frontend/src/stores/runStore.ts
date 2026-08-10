import { create } from 'zustand';
import type {
  AgentEvent,
  ApprovalView,
  RunEvent,
  RunPath,
  RunSnapshot,
  RunStatus,
  RunStep,
} from '@/types/api/runs';

type RuntimeEvent = RunEvent | AgentEvent;

export interface RunProjection {
  run: RunSnapshot | null;
  tokens: string;
  upgradeReason?: string;
  recovered: boolean;
  diagnostics: string[];
  events: string[];
  /**
   * 审批已提交、运行尚未回到流式的窗口。纯客户端状态：后端在批准的瞬间就迁移到
   * running_structured，但那要等一个 HTTP 往返才看得到，中间不能让审批卡片一直杵着。
   */
  resuming?: { approvalId: string; approved: boolean };
}
export const INITIAL_RUN_STATE: RunProjection = {
  run: null,
  tokens: '',
  diagnostics: [],
  events: [],
  recovered: false,
};

/** 运行已经停下、不会再有副作用的状态。删除消息等破坏性操作只在这之后才安全。 */
export const TERMINAL_RUN_STATUSES = new Set<RunStatus>(['completed', 'failed', 'cancelled']);
const terminal = TERMINAL_RUN_STATUSES;
const statusFor = (type: string): RunStatus | undefined =>
  ({
    'run.controlled_started': 'running_structured',
    'run.completed': 'completed',
    'run.failed': 'failed',
    'run.cancelling': 'cancelling',
    'run.cancelled': 'cancelled',
    'run.waiting_approval': 'waiting_approval',
    'run.waiting_external': 'waiting_external',
    'run.reconciling': 'reconciling',
  })[type] as RunStatus | undefined;
const stepStatus = (type: string): RunStep['status'] | undefined =>
  ({ 'step.started': 'running', 'step.succeeded': 'succeeded', 'step.failed': 'failed' })[type] as
    | RunStep['status']
    | undefined;

function reduceRunEventCore(state: RunProjection, event: RuntimeEvent): RunProjection {
  const eventType = event.event_type ?? event.type ?? '';
  const data: Record<string, unknown> = event.payload ?? event.data ?? {};
  const references = event.references ?? {};
  if (eventType === 'run.created') {
    if (state.run) return state;
    const snapshot = data as unknown as Partial<RunSnapshot>;
    if (!snapshot.run_id || !snapshot.status || !snapshot.path)
      return {
        ...state,
        diagnostics: [...state.diagnostics, 'Received partial run.created event'],
      };
    return {
      ...state,
      run: {
        ...(snapshot as RunSnapshot),
        steps: snapshot.steps ?? {},
        pending_approvals: snapshot.pending_approvals ?? [],
      },
      recovered: snapshot.intent?.source === 'resume',
    };
  }
  // A v2 RUN_CREATED follows the POST snapshot already installed by setRun.
  if (eventType === 'RUN_CREATED') return state;
  if (!state.run)
    return {
      ...state,
      diagnostics: [...state.diagnostics, `Ignored ${eventType} before run snapshot`],
    };
  if (eventType === 'RUN_STATUS_CHANGED') {
    const status = data.to as RunStatus | undefined;
    if (!status) return state;
    return {
      ...state,
      upgradeReason:
        state.run.path === 'fast' && status === 'running_structured'
          ? String(data.reason ?? '')
          : state.upgradeReason,
      run: {
        ...state.run,
        path: status === 'running_structured' ? 'structured' : state.run.path,
        status,
      },
      diagnostics:
        status === 'failed' && data.reason
          ? [...state.diagnostics, String(data.reason)]
          : state.diagnostics,
    };
  }
  if (eventType === 'ASSISTANT_MESSAGE') {
    const content = String(data.content ?? '');
    return { ...state, tokens: content, run: { ...state.run, final_text: content } };
  }
  if (eventType === 'PLAN_CREATED' && Array.isArray(data.tasks)) {
    const statuses: Record<string, RunStep['status']> = {
      pending: 'pending',
      ready: 'ready',
      in_progress: 'running',
      blocked: 'waiting_external',
      completed: 'succeeded',
      failed: 'failed',
      skipped: 'skipped',
    };
    const steps = Object.fromEntries(
      data.tasks
        .filter(
          (item): item is Record<string, unknown> => typeof item === 'object' && item !== null,
        )
        .map((item) => {
          const id = String(item.task_id ?? 'task');
          return [
            id,
            {
              step_id: id,
              kind: String(item.title ?? 'task'),
              status: statuses[String(item.status)] ?? 'pending',
            },
          ];
        }),
    );
    return { ...state, run: { ...state.run, steps: { ...state.run.steps, ...steps } } };
  }
  if (eventType === 'ERROR')
    return { ...state, diagnostics: [...state.diagnostics, String(data.code ?? 'runtime_error')] };

  const projectedType =
    eventType === 'TOOL_CALL'
      ? 'step.started'
      : eventType === 'TOOL_RESULT'
        ? data.status === 'succeeded'
          ? 'step.succeeded'
          : 'step.failed'
        : eventType === 'APPROVAL_REQUESTED'
          ? 'approval.requested'
          : eventType === 'APPROVAL_RESOLVED'
            ? 'approval.resolved'
            : eventType;
  if (eventType === 'TOOL_CALL' || eventType === 'TOOL_RESULT') {
    data.step_id = data.call_id ?? references.call_id;
    data.name = data.tool_id;
    data.error_message = data.error;
  }
  if (eventType === 'APPROVAL_RESOLVED')
    data.status = data.approved === false ? 'rejected' : 'approved';

  if (projectedType === 'token.delta')
    return { ...state, tokens: state.tokens + String(data.delta ?? '') };
  if (projectedType === 'run.path_selected')
    return { ...state, run: { ...state.run, path: data.path as RunPath } };
  if (projectedType === 'run.path_upgraded')
    return {
      ...state,
      run: { ...state.run, path: 'structured', status: 'running_structured' },
      upgradeReason: String(data.reason ?? ''),
    };
  const newStepStatus = stepStatus(projectedType);
  if (newStepStatus) {
    const existingSteps = Object.values(state.run.steps);
    const runningSteps = existingSteps.filter((step) => step.status === 'running');
    const namedStep =
      typeof data.name === 'string'
        ? (existingSteps.find((step) => step.kind === data.name) ??
          (runningSteps.length === 1 ? runningSteps[0] : undefined))
        : undefined;
    const stepId = String(
      data.step_id ?? data.capability_id ?? namedStep?.step_id ?? data.name ?? 'runtime',
    );
    const previous = state.run.steps[stepId] ?? {
      step_id: stepId,
      kind: String(data.kind ?? 'capability'),
      status: 'pending' as const,
    };
    return {
      ...state,
      run: {
        ...state.run,
        steps: {
          ...state.run.steps,
          [stepId]: {
            ...previous,
            kind: String(data.kind ?? data.name ?? previous.kind),
            status: newStepStatus,
            error_message: data.error_message as string | undefined,
          },
        },
      },
    };
  }
  if (projectedType === 'approval.requested') {
    // 下一轮确认（或重开的一轮）到了，恢复态到此为止，让新卡片正常出现。
    if (!data.approval_id)
      return {
        ...state,
        resuming: undefined,
        diagnostics: [...state.diagnostics, 'Approval detail will be loaded from snapshot'],
      };
    const approval = data as unknown as ApprovalView;
    return {
      ...state,
      resuming: undefined,
      run: {
        ...state.run,
        status: 'waiting_approval',
        pending_approvals: [
          ...state.run.pending_approvals.filter(
            (item) => item.approval_id !== approval.approval_id,
          ),
          approval,
        ],
      },
    };
  }
  if (projectedType === 'approval.resolved' || projectedType === 'approval.expired') {
    const approvalId = String(data.approval_id ?? '');
    return {
      ...state,
      run: {
        ...state.run,
        pending_approvals: state.run.pending_approvals.map((item) =>
          item.approval_id === approvalId
            ? {
                ...item,
                status:
                  projectedType === 'approval.expired'
                    ? 'expired'
                    : ((data.status as ApprovalView['status']) ?? 'approved'),
              }
            : item,
        ),
      },
    };
  }
  if (projectedType === 'artifact.created') return state;
  if (projectedType === 'context.shed')
    // The runtime demoted old tool results to artifact references to stay
    // inside its token budget. Worth surfacing — context was dropped from the
    // prompt — but it changes no run state.
    return {
      ...state,
      diagnostics: [
        ...state.diagnostics,
        `上下文裁剪 · ${String(data.total_tokens ?? '')}/${String(data.limit ?? '')} tokens`,
      ],
    };
  const runStatus = statusFor(projectedType);
  if (runStatus)
    return {
      ...state,
      resuming: runStatus === 'running_structured' ? state.resuming : undefined,
      run: {
        ...state.run,
        status: runStatus,
        final_text: terminal.has(runStatus)
          ? String(data.final_text ?? state.tokens)
          : state.run.final_text,
      },
      diagnostics:
        projectedType === 'run.failed' && (data.reason || data.error_message)
          ? [...state.diagnostics, String(data.reason ?? data.error_message)]
          : state.diagnostics,
    };
  return state;
}

function eventSummary(event: RuntimeEvent): string | undefined {
  const eventType = event.event_type ?? event.type ?? '';
  if (eventType === 'token.delta') return undefined;
  const data = (event.payload ?? event.data ?? {}) as Record<string, unknown>;
  const details: unknown[] =
    eventType === 'TOOL_CALL' || eventType === 'TOOL_RESULT'
      ? [data.tool_id ?? data.name, eventType === 'TOOL_RESULT' ? data.status : undefined]
      : eventType === 'TOOL_SEARCH'
        ? [data.query]
        : eventType === 'SKILL_ACTIVATED'
          ? [data.skill_id]
          : eventType === 'RUN_STATUS_CHANGED'
            ? [data.to, data.reason]
            : eventType === 'ERROR'
              ? [data.code]
              : [
                  data.name ??
                    data.kind ??
                    data.path ??
                    data.reason ??
                    data.status ??
                    data.step_id ??
                    data.capability_id,
                ];
  return [eventType, ...details]
    .filter((value) => value !== undefined && value !== null && value !== '')
    .map(String)
    .join(' · ');
}

export function reduceRunEvent(state: RunProjection, event: RuntimeEvent): RunProjection {
  const next = reduceRunEventCore(state, event);
  const summary = eventSummary(event);
  return summary ? { ...next, events: [...next.events, summary].slice(-100) } : next;
}
export function reduceRunEvents(state: RunProjection, events: RuntimeEvent[]) {
  return events.reduce(reduceRunEvent, state);
}

/**
 * 恢复态只在「这一次审批解开的那段执行」内有效：运行重新停下来要人（新一轮确认）
 * 或者已经走到头，它就该让位给真实状态。
 */
function stillResuming(
  resuming: RunProjection['resuming'],
  snapshot: RunSnapshot,
): RunProjection['resuming'] {
  if (!resuming) return undefined;
  if (
    terminal.has(snapshot.status) ||
    snapshot.status === 'waiting_external' ||
    snapshot.status === 'reconciling' ||
    snapshot.status === 'cancelling'
  )
    return undefined;
  const reopened = snapshot.pending_approvals.some(
    (item) => item.status === 'pending' && item.approval_id !== resuming.approvalId,
  );
  return reopened ? undefined : resuming;
}

function mergeSnapshot(state: RunProjection, snapshot: RunSnapshot | null): RunProjection {
  if (!snapshot) return { ...INITIAL_RUN_STATE, run: null };
  const current = state.run;
  if (current?.run_id === snapshot.run_id) {
    if (terminal.has(current.status) && !terminal.has(snapshot.status)) return state;
    if (snapshot.revision < current.revision) return state;
  }
  return {
    ...state,
    resuming: stillResuming(state.resuming, snapshot),
    run: { ...snapshot, steps: { ...(current?.steps ?? {}), ...(snapshot.steps ?? {}) } },
    recovered: state.recovered || snapshot.intent?.source === 'resume',
  };
}
interface RunStore extends RunProjection {
  apply: (event: RuntimeEvent) => void;
  diagnose: (message: string) => void;
  setRun: (run: RunSnapshot | null) => void;
  mergeRun: (run: RunSnapshot) => void;
  markApprovalSubmitted: (approvalId: string, approved: boolean) => void;
  clearResuming: () => void;
  markRecovered: () => void;
  reset: () => void;
}
export const useRunStore = create<RunStore>((set) => ({
  ...INITIAL_RUN_STATE,
  apply: (event) => set((state) => reduceRunEvent(state, event)),
  diagnose: (message) => set((state) => ({ diagnostics: [...state.diagnostics, message] })),
  setRun: (run) => set({ ...INITIAL_RUN_STATE, run, recovered: run?.intent?.source === 'resume' }),
  mergeRun: (run) => set((state) => mergeSnapshot(state, run)),
  markApprovalSubmitted: (approvalId, approved) => set({ resuming: { approvalId, approved } }),
  clearResuming: () => set({ resuming: undefined }),
  markRecovered: () => set({ recovered: true }),
  reset: () => set(INITIAL_RUN_STATE),
}));
