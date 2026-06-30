import type { SolveRequest, SolveRun, SolveRunList } from '@/types';
import { apiGet, apiPost, withQuery } from './client';

/** `POST /planning/solve` — submit a solve, returns the resulting SolveRun. */
export function solve(req: SolveRequest, signal?: AbortSignal): Promise<SolveRun> {
  return apiPost<SolveRun>('/planning/solve', req, { signal });
}

/** `GET /planning/solve-runs` — SolveRun history for multi-version comparison. */
export function getSolveRuns(sessionId: string, signal?: AbortSignal): Promise<SolveRunList> {
  return apiGet<SolveRunList>(withQuery('/planning/solve-runs', { session_id: sessionId }), { signal });
}
