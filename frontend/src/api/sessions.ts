import { apiGet, apiPost } from './client';
export interface SessionSummary { session_id: string; title: string; updated_at: string; message_count: number; active_run_id?: string | null }
export const listSessions = (signal?: AbortSignal) => apiGet<SessionSummary[]>('/sessions', { signal });
export const createSession = (title = '新任务') => apiPost<SessionSummary>('/sessions', { title });
export interface SessionMessage { role: 'user' | 'assistant' | 'system'; content: string; ts: string; artifact_ids?: string[]; skill_names?: string[] }
export const getSessionMessages = (sessionId: string, signal?: AbortSignal) => apiGet<SessionMessage[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`, { signal });
