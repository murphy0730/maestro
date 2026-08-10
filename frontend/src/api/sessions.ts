import { AGENT_API_PREFIX, apiDelete, apiGet, apiPatch, apiPost } from './client';
export interface SessionSummary {
  session_id: string;
  title: string;
  updated_at: string;
  message_count: number;
  active_run_id?: string | null;
}
export const listSessions = (signal?: AbortSignal) =>
  apiGet<SessionSummary[]>(`${AGENT_API_PREFIX}/sessions`, { signal });
export const createSession = (title = '新任务') => apiPost<SessionSummary>(`${AGENT_API_PREFIX}/sessions`, { title });
export const renameSession = (sessionId: string, title: string) =>
  apiPatch<SessionSummary>(`${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}`, { title });
export const deleteSession = (sessionId: string) =>
  apiDelete<{ deleted: true; session_id: string }>(`${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}`);
export const deleteSessionMessage = (sessionId: string, messageId: string, cascade = false) =>
  apiDelete<{ redacted?: true; event_ids?: string[]; deleted_ids?: string[] }>(
    `${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}${cascade ? '?cascade=true' : ''}`,
  ).then((result) => ({
    deleted: true as const,
    session_id: sessionId,
    deleted_ids: result.event_ids ?? result.deleted_ids ?? [],
  }));
export interface SessionMessage {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: string;
  artifact_ids?: string[];
  skill_names?: string[];
  run_id?: string | null;
}
export const getSessionMessages = (sessionId: string, signal?: AbortSignal) =>
  apiGet<Array<{ event_id: string; event_type: 'USER_MESSAGE' | 'ASSISTANT_MESSAGE'; payload: Record<string, unknown>; created_at: string; run_id?: string | null }>>(
    `${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/messages`,
    { signal },
  ).then((events) =>
    events.map((event) => ({
      id: event.event_id,
      role: event.event_type === 'USER_MESSAGE' ? 'user' as const : 'assistant' as const,
      content: String(event.payload.content ?? ''),
      ts: event.created_at,
      artifact_ids: Array.isArray(event.payload.artifact_ids) ? event.payload.artifact_ids.map(String) : [],
      skill_names: Array.isArray(event.payload.skill_ids) ? event.payload.skill_ids.map(String) : [],
      run_id: event.run_id,
    })),
  );
