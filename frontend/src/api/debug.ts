import { AGENT_API_PREFIX, apiGet } from './client';
import type { AgentEvent, RunSnapshot } from '@/types/api/runs';

export interface RuntimeDebugResponse {
  run: RunSnapshot;
  events: AgentEvent[];
  plan: null | { plan: Record<string, unknown>; tasks: Array<Record<string, unknown>> };
  approvals: Array<Record<string, unknown>>;
  context_manifests: Array<Record<string, unknown>>;
  checkpoint: null | Record<string, unknown>;
}

export interface ReplayReport {
  valid: boolean;
  errors: string[];
  event_count: number;
  last_sequence: number;
  checkpoint_id?: string | null;
  prefix_hash: string;
  context_hashes: string[];
}

export const getRunDebug = (runId: string, signal?: AbortSignal) =>
  apiGet<RuntimeDebugResponse>(`${AGENT_API_PREFIX}/runs/${encodeURIComponent(runId)}/debug`, {
    signal,
  });

export const replaySession = (sessionId: string, signal?: AbortSignal) =>
  apiGet<ReplayReport>(
    `${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/replay`,
    { signal },
  );
