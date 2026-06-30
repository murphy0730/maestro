import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  ExecuteActionRequest,
  ExecuteActionResponse,
  SolveRequest,
  SolveRun,
} from '@/types';
import { queryKeys } from './queryKeys';
import { getSolveRuns, solve } from './planning';
import { executeAction, getDispatchOrders, getExceptionImpact, getKitting } from './scheduling';
import { getAuditTimeline } from './query';

/* ============================================================
   Planning
   ============================================================ */

/** SolveRun history for a session (multi-version KPI comparison). */
export function useSolveRuns(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.planning.solveRuns(sessionId),
    queryFn: ({ signal }) => getSolveRuns(sessionId, signal),
    enabled: enabled && !!sessionId,
  });
}

/** Submit a planning solve; refreshes the SolveRun history on success. */
export function useSolveMutation(sessionId: string) {
  const qc = useQueryClient();
  return useMutation<SolveRun, Error, SolveRequest>({
    mutationFn: (req) => solve(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.planning.solveRuns(sessionId) });
    },
  });
}

/* ============================================================
   Scheduling
   ============================================================ */

export function useKitting(sessionId: string, scope?: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.scheduling.kitting(sessionId, scope),
    queryFn: ({ signal }) => getKitting(sessionId, scope, signal),
    enabled: enabled && !!sessionId,
  });
}

export function useDispatchOrders(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.scheduling.dispatchOrders(sessionId),
    queryFn: ({ signal }) => getDispatchOrders(sessionId, signal),
    enabled: enabled && !!sessionId,
  });
}

export function useExceptionImpact(sessionId: string, eventId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.scheduling.exceptionImpact(sessionId, eventId),
    queryFn: ({ signal }) => getExceptionImpact(sessionId, eventId, signal),
    enabled: enabled && !!sessionId && !!eventId,
  });
}

/** Execute a dispatch action; refreshes the dispatch-order list afterwards. */
export function useExecuteAction(sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ExecuteActionResponse, Error, ExecuteActionRequest>({
    mutationFn: (req) => executeAction(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.scheduling.dispatchOrders(sessionId) });
    },
  });
}

/* ============================================================
   Observability
   ============================================================ */

export function useAuditTimeline(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.audit.timeline(sessionId),
    queryFn: ({ signal }) => getAuditTimeline(sessionId, signal),
    enabled: enabled && !!sessionId,
  });
}
