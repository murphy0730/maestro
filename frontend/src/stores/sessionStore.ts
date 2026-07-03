import { create } from 'zustand';

export interface SessionInfo {
  session_id: string;
  title: string;
  engine: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface SessionStoreState {
  sessions: SessionInfo[];
  activeSessionId: string | null;
  setSessions: (sessions: SessionInfo[]) => void;
  upsertSession: (session: SessionInfo) => void;
  removeSession: (id: string) => void;
  setActiveSessionId: (id: string | null) => void;
}

export const useSessionStore = create<SessionStoreState>((set) => ({
  sessions: [],
  activeSessionId: null,

  setSessions: (sessions) => set({ sessions }),

  upsertSession: (session) =>
    set((s) => {
      const idx = s.sessions.findIndex((x) => x.session_id === session.session_id);
      const next = [...s.sessions];
      if (idx >= 0) {
        next[idx] = session;
      } else {
        next.unshift(session);
      }
      return { sessions: next };
    }),

  removeSession: (id) => set((s) => ({ sessions: s.sessions.filter((x) => x.session_id !== id) })),

  setActiveSessionId: (id) => set({ activeSessionId: id }),
}));
