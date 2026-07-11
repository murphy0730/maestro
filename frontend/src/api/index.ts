/**
 * API layer — backend contract client (see docs/api-contract/api-contract.md).
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
export { streamChat, clarifyChat, confirmChatAction } from './chat';
export { solve, getSolveRuns } from './planning';
export {
  getKitting,
  getDispatchOrders,
  executeAction,
  getExceptionImpact,
  getObservation,
} from './scheduling';
export { streamQuery, getAuditTimeline } from './query';
export {
  listKnowledge,
  uploadKnowledge,
  replaceKnowledge,
  renameKnowledge,
  deleteKnowledge,
} from './knowledge';
export {
  listSkills,
  importSkill,
  validateSkill,
  trustSkill,
  revokeSkillTrust,
  deleteSkill,
} from './skills';
export {
  listConnectors,
  createConnector,
  deleteConnector,
  connectConnector,
  disconnectConnector,
  testConnector,
} from './connectors';
export {
  addCatalogConnector,
  getCatalogStatus,
  installCatalogSkill,
  listCatalogConnectors,
  listCatalogSkills,
  listCatalogSources,
  previewCatalogConnectorUpdate,
  syncCatalog,
  updateCatalogConnector,
} from './extensionCatalog';

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
  useSessions,
  useCreateSession,
  useRenameSession,
  useDeleteSession,
  useKnowledgeDocs,
  useUploadKnowledge,
  useReplaceKnowledge,
  useRenameKnowledge,
  useDeleteKnowledge,
  useSkills,
  useImportSkill,
  useTrustSkill,
  useDeleteSkill,
} from './hooks';

// Streaming hooks
export { useStreamingChat, type StreamingChatState, type StreamPhase } from './useStreamingChat';
export { useStreamingQuery, type StreamingQueryState } from './useStreamingQuery';
export { listSessions, createSession, getSessionMessages } from './sessions';
export type { StoredMessage } from './sessions';
