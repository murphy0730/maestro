/**
 * API layer — backend contract client (see docs/api-contract.md).
 * Plain request fns, TanStack Query hooks, and SSE streaming hooks.
 */
export { API_BASE, ApiError, apiGet, apiPost, withQuery } from './client';
export { streamSse, type SseMessage } from './streaming';

// Raw endpoint functions
export { streamChat, clarifyChat } from './chat';
export { solve, getSolveRuns } from './planning';
export { getKitting, getDispatchOrders, executeAction, getExceptionImpact } from './scheduling';
export { streamQuery, getAuditTimeline } from './query';

// Query keys + TanStack Query hooks
export { queryKeys } from './queryKeys';
export {
  useSolveRuns,
  useSolveMutation,
  useKitting,
  useDispatchOrders,
  useExceptionImpact,
  useExecuteAction,
  useAuditTimeline,
} from './hooks';

// Streaming hooks
export { useStreamingChat, type StreamingChatState, type StreamPhase } from './useStreamingChat';
export { useStreamingQuery, type StreamingQueryState } from './useStreamingQuery';
export { listSessions, createSession, getSessionMessages } from './sessions';
export type { StoredMessage } from './sessions';
