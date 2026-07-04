import { create } from 'zustand';

/** Backend SessionMeta shape (docs/api-contract-v2.md §5). */
export interface SessionInfo {
  session_id: string;
  title: string;
  engine: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/**
 * Client-only session UI state. The session *list* is server state and lives
 * in the TanStack Query cache (`useSessions` in `@/api`); this store keeps
 * only which session is active.
 */
interface SessionStoreState {
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
}

export const useSessionStore = create<SessionStoreState>((set) => ({
  activeSessionId: null,
  setActiveSessionId: (id) => set({ activeSessionId: id }),
}));
