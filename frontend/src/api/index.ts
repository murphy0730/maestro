/**
 * API layer — backend contract client (see docs/api-contract.md).
 * Plain request fns, TanStack Query hooks, and SSE streaming hooks.
 */
export {
  API_BASE,
  ApiError,
  apiGet,
  apiPost,
  apiDelete,
  apiUpload,
  withQuery,
  type UploadOptions,
} from './client';
export { streamSse, type SseMessage } from './streaming';

// Raw endpoint functions
export { streamChat, clarifyChat } from './chat';
export { solve, getSolveRuns } from './planning';
export { getKitting, getDispatchOrders, executeAction, getExceptionImpact } from './scheduling';
export { streamQuery, getAuditTimeline } from './query';
export {
  listKnowledge,
  uploadKnowledge,
  replaceKnowledge,
  renameKnowledge,
  deleteKnowledge,
} from './knowledge';

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
  useKnowledgeDocs,
  useUploadKnowledge,
  useReplaceKnowledge,
  useRenameKnowledge,
  useDeleteKnowledge,
} from './hooks';

// Streaming hooks
export { useStreamingChat, type StreamingChatState, type StreamPhase } from './useStreamingChat';
export { useStreamingQuery, type StreamingQueryState } from './useStreamingQuery';
