import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  ExecuteActionRequest,
  ExecuteActionResponse,
  KnowledgeDoc,
  KnowledgeListResponse,
  SkillMeta,
  SolveRequest,
  SolveRun,
} from '@/types';
import type { UploadOptions } from './client';
import { queryKeys } from './queryKeys';
import { getSolveRuns, solve } from './planning';
import { executeAction, getDispatchOrders, getExceptionImpact, getKitting } from './scheduling';
import { getAuditTimeline } from './query';
import {
  deleteKnowledge,
  listKnowledge,
  renameKnowledge,
  replaceKnowledge,
  uploadKnowledge,
} from './knowledge';
import { deleteSkill, importSkill, listSkills } from './skills';
import { createSession, deleteSession, listSessions, renameSession } from './sessions';
import type { SessionInfo } from '@/stores/sessionStore';

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

/* ============================================================
   Sessions (conversation list CRUD)
   ============================================================ */

/** All sessions, most recently updated first (drives the sidebar). */
export function useSessions() {
  return useQuery({
    queryKey: queryKeys.sessions.list(),
    queryFn: () => listSessions(),
  });
}

/** Create a session and prepend it to the cached list. */
export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation<SessionInfo, Error, string | undefined>({
    mutationFn: (title) => createSession(title ?? '新对话'),
    onSuccess: (s) =>
      qc.setQueryData<SessionInfo[]>(queryKeys.sessions.list(), (prev) => [s, ...(prev ?? [])]),
  });
}

/** Rename a session, updating it in place in the cached list. */
export function useRenameSession() {
  const qc = useQueryClient();
  return useMutation<SessionInfo, Error, { id: string; title: string }>({
    mutationFn: ({ id, title }) => renameSession(id, title),
    onSuccess: (updated) =>
      qc.setQueryData<SessionInfo[]>(queryKeys.sessions.list(), (prev) =>
        (prev ?? []).map((s) => (s.session_id === updated.session_id ? updated : s)),
      ),
  });
}

/** Delete a session, optimistically dropping it from the cached list. */
export function useDeleteSession() {
  const qc = useQueryClient();
  const key = queryKeys.sessions.list();
  return useMutation<
    { deleted: boolean; session_id: string },
    Error,
    string,
    { prev?: SessionInfo[] }
  >({
    mutationFn: (id) => deleteSession(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<SessionInfo[]>(key);
      if (prev) {
        qc.setQueryData<SessionInfo[]>(key, prev.filter((s) => s.session_id !== id));
      }
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

/* ============================================================
   Knowledge base (RAG documents CRUD)
   ============================================================ */

/** List knowledge-base documents (drives the RAG management panel). */
export function useKnowledgeDocs(enabled = true) {
  return useQuery({
    queryKey: queryKeys.knowledge.list(),
    queryFn: ({ signal }) => listKnowledge(signal),
    enabled,
  });
}

/** Upload a file; onProgress drives the per-file progress bar. */
export function useUploadKnowledge() {
  const qc = useQueryClient();
  return useMutation<KnowledgeDoc, Error, { file: File; opts?: UploadOptions }>({
    mutationFn: ({ file, opts }) => uploadKnowledge(file, opts),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.knowledge.list() }),
  });
}

/** Replace a document's content (change). */
export function useReplaceKnowledge() {
  const qc = useQueryClient();
  return useMutation<KnowledgeDoc, Error, { docId: string; file: File; opts?: UploadOptions }>({
    mutationFn: ({ docId, file, opts }) => replaceKnowledge(docId, file, opts),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.knowledge.list() }),
  });
}

/** Rename a document (change). */
export function useRenameKnowledge() {
  const qc = useQueryClient();
  return useMutation<KnowledgeDoc, Error, { docId: string; name: string }>({
    mutationFn: ({ docId, name }) => renameKnowledge(docId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.knowledge.list() }),
  });
}

/** Delete a document, optimistically dropping it from the cached list. */
export function useDeleteKnowledge() {
  const qc = useQueryClient();
  const key = queryKeys.knowledge.list();
  return useMutation<{ doc_id: string; removed_chunks: number }, Error, string, { prev?: KnowledgeListResponse }>({
    mutationFn: (docId) => deleteKnowledge(docId),
    onMutate: async (docId) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<KnowledgeListResponse>(key);
      if (prev) {
        qc.setQueryData<KnowledgeListResponse>(key, {
          ...prev,
          docs: prev.docs.filter((d) => d.doc_id !== docId),
        });
      }
      return { prev };
    },
    onError: (_e, _docId, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

/* ============================================================
   Skills (skill package registry CRUD)
   ============================================================ */

/** List registered skill packages (drives the skills management panel). */
export function useSkills() {
  return useQuery({
    queryKey: queryKeys.skills.list(),
    queryFn: () => listSkills(),
  });
}

/** Import a skill bundle file; onProgress drives the progress bar. */
export function useImportSkill() {
  const qc = useQueryClient();
  return useMutation<SkillMeta, Error, File>({
    mutationFn: (file) => importSkill(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.skills.list() }),
  });
}

/** Delete a skill package by name; refreshes the list on success. */
export function useDeleteSkill() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => deleteSkill(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.skills.list() }),
  });
}
