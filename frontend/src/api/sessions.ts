import type { SessionInfo } from '@/stores/sessionStore';
import { apiGet, apiPost, apiPatch, apiDelete } from './client';

export interface StoredMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: string;
  kind?: 'normal' | 'system';
}

export const listSessions = () => apiGet<SessionInfo[]>('/sessions');

export const createSession = (title = '新对话') => apiPost<SessionInfo>('/sessions', { title });

export const getSessionMessages = (sessionId: string) =>
  apiGet<StoredMessage[]>(`/sessions/${sessionId}/messages`);

export const renameSession = (sessionId: string, title: string) =>
  apiPatch<SessionInfo>(`/sessions/${sessionId}`, { title });

export const deleteSession = (sessionId: string) =>
  apiDelete<{ deleted: boolean; session_id: string }>(`/sessions/${sessionId}`);
