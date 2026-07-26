import { useCallback, useEffect, useState } from 'react';
import {
  createSession,
  deleteSession,
  listSessions,
  renameSession,
  type SessionSummary,
} from '@/api';
import { useSessionStore } from '@/stores/sessionStore';

/**
 * Session list + CRUD, shared by the Workspace and the Extensions Center so the
 * sidebar behaves identically on both routes. The Workspace keeps message
 * loading and the run stream; only what the sidebar needs lives here.
 */
export function useWorkspaceSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);

  const refresh = useCallback(async () => {
    const result = await listSessions();
    setSessions(result);
    return result;
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void refresh()
      .then(async (result) => {
        if (!active) return;
        const savedSessionId = useSessionStore.getState().activeSessionId;
        const first =
          result.find((session) => session.session_id === savedSessionId) ??
          result[0] ??
          (await createSession('新任务'));
        if (!active) return;
        if (result.length === 0) setSessions([first]);
        setSessionId(first.session_id);
        setActiveSessionId(first.session_id);
      })
      .catch((cause) => active && setError(messageOf(cause, '无法加载会话')))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [refresh, setActiveSessionId]);

  const create = useCallback(async () => {
    setError(undefined);
    try {
      const created = await createSession('新任务');
      setSessions((items) => [created, ...items]);
      setSessionId(created.session_id);
      return created;
    } catch (cause) {
      setError(messageOf(cause, '新建会话失败'));
      return undefined;
    }
  }, []);

  const rename = useCallback(async (id: string, title: string) => {
    try {
      const updated = await renameSession(id, title);
      setSessions((items) => items.map((item) => (item.session_id === id ? updated : item)));
    } catch (cause) {
      setError(messageOf(cause, '重命名失败'));
    }
  }, []);

  const remove = useCallback(
    async (id: string) => {
      const target = sessions.find((item) => item.session_id === id);
      if (!target || !window.confirm(`确定删除会话“${target.title}”？此操作会删除其历史消息。`))
        return;
      try {
        await deleteSession(id);
        const remaining = sessions.filter((item) => item.session_id !== id);
        setSessions(remaining);
        if (id === sessionId) {
          const next = remaining[0] ?? (await createSession('新任务'));
          if (remaining.length === 0) setSessions([next]);
          setSessionId(next.session_id);
        }
      } catch (cause) {
        setError(messageOf(cause, '删除会话失败'));
      }
    },
    [sessionId, sessions],
  );

  return {
    sessions,
    setSessions,
    sessionId,
    setSessionId,
    loading,
    error,
    setError,
    refresh,
    create,
    rename,
    remove,
  };
}

export function messageOf(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
