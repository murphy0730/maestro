import { apiGet, apiPost } from './client';
export interface SessionSummary { session_id: string; title: string; updated_at: string; message_count: number }
export const listSessions = () => apiGet<SessionSummary[]>('/sessions');
export const createSession = (title = '新任务') => apiPost<SessionSummary>('/sessions', { title });
