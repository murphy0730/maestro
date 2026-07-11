import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useCreateSession, useDeleteSession, useRenameSession, useSessions } from '@/api';
import { getSessionMessages } from '@/api/sessions';
import { storedToThread } from '@/features/orchestrator/history';
import type { ConversationSummary } from '@/mocks/session';
import { useConversationStore } from '@/stores';
import { useSessionStore } from '@/stores/sessionStore';
import type { RouteEngine } from '@/types';

interface UseWorkspaceSessionsOptions {
  onFreshConversation: () => void;
}

export function useWorkspaceSessions({ onFreshConversation }: UseWorkspaceSessionsOptions) {
  const resetThread = useConversationStore((state) => state.resetThread);
  const activeSessionId = useSessionStore((state) => state.activeSessionId);
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);
  const sessionsQuery = useSessions();
  const sessions = useMemo(() => sessionsQuery.data ?? [], [sessionsQuery.data]);
  const createSession = useCreateSession();
  const renameSession = useRenameSession();
  const deleteSession = useDeleteSession();
  const [isLoading, setIsLoading] = useState(false);
  const [isSessionReady, setIsSessionReady] = useState(false);
  const loadRequestRef = useRef(0);

  const fallbackIdRef = useRef(crypto.randomUUID().replace(/-/g, ''));
  const currentSessionId = activeSessionId ?? fallbackIdRef.current;

  const loadSession = useCallback(
    async (sessionId: string) => {
      const requestId = ++loadRequestRef.current;
      const messagesBeforeLoad = useConversationStore.getState().messages;
      setIsLoading(true);
      try {
        const stored = await getSessionMessages(sessionId);
        if (
          requestId !== loadRequestRef.current ||
          useConversationStore.getState().messages !== messagesBeforeLoad
        ) {
          return;
        }
        resetThread(storedToThread(stored));
      } catch {
        if (
          requestId !== loadRequestRef.current ||
          useConversationStore.getState().messages !== messagesBeforeLoad
        ) {
          return;
        }
        resetThread();
      } finally {
        if (requestId === loadRequestRef.current) setIsLoading(false);
      }
    },
    [resetThread],
  );

  const initializedRef = useRef(false);
  useEffect(() => {
    if (sessionsQuery.isError) setIsSessionReady(true);
  }, [sessionsQuery.isError]);

  useEffect(() => {
    if (initializedRef.current || !sessionsQuery.isSuccess) return;
    initializedRef.current = true;

    const initialize = async () => {
      const fetched = sessionsQuery.data;
      if (fetched.length > 0) {
        const recent = fetched[0];
        setActiveSessionId(recent.session_id);
        await loadSession(recent.session_id);
        return;
      }
      const newSession = await createSession.mutateAsync('新对话').catch(() => null);
      if (newSession) {
        setActiveSessionId(newSession.session_id);
        resetThread();
      }
    };
    void initialize().finally(() => setIsSessionReady(true));
  }, [
    createSession,
    loadSession,
    resetThread,
    sessionsQuery.data,
    sessionsQuery.isSuccess,
    setActiveSessionId,
  ]);

  const handleNewConversation = useCallback(async () => {
    setIsSessionReady(false);
    const newSession = await createSession.mutateAsync('新对话').catch(() => null);
    if (newSession) {
      setActiveSessionId(newSession.session_id);
    }
    resetThread();
    onFreshConversation();
    setIsSessionReady(true);
  }, [createSession, onFreshConversation, resetThread, setActiveSessionId]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      if (id === activeSessionId) return;
      setIsSessionReady(false);
      setActiveSessionId(id);
      await loadSession(id);
      setIsSessionReady(true);
    },
    [activeSessionId, loadSession, setActiveSessionId],
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      try {
        await renameSession.mutateAsync({ id, title });
      } catch {
        return;
      }
    },
    [renameSession],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteSession.mutateAsync(id);
      } catch {
        return;
      }
      if (id !== activeSessionId) return;

      const remaining = sessions.filter((session) => session.session_id !== id);
      if (remaining.length > 0) {
        setActiveSessionId(remaining[0].session_id);
        await loadSession(remaining[0].session_id);
        return;
      }

      try {
        const newSession = await createSession.mutateAsync('新对话');
        setActiveSessionId(newSession.session_id);
      } catch {
        setActiveSessionId(null);
      }
      resetThread();
      onFreshConversation();
    },
    [
      activeSessionId,
      createSession,
      deleteSession,
      loadSession,
      onFreshConversation,
      resetThread,
      sessions,
      setActiveSessionId,
    ],
  );

  const sidebarConversations: ConversationSummary[] = useMemo(
    () =>
      sessions.map((session) => ({
        id: session.session_id,
        title: session.title,
        engine: (session.engine as RouteEngine | null) ?? null,
        time: formatRelativeTime(session.updated_at),
      })),
    [sessions],
  );

  return {
    activeSession: sessions.find((session) => session.session_id === activeSessionId),
    activeSessionId,
    currentSessionId,
    handleDeleteSession,
    handleNewConversation,
    handleRenameSession,
    handleSelectSession,
    isLoading,
    isSessionReady,
    refetchSessions: sessionsQuery.refetch,
    sidebarConversations,
  };
}

function formatRelativeTime(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const differenceMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);
    if (differenceMinutes < 2) return '刚刚';
    if (differenceMinutes < 60) return `${differenceMinutes} 分钟前`;

    const isSameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();
    if (isSameDay) return date.toLocaleTimeString('en-GB').slice(0, 5);

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday =
      date.getFullYear() === yesterday.getFullYear() &&
      date.getMonth() === yesterday.getMonth() &&
      date.getDate() === yesterday.getDate();
    if (isYesterday) return '昨天';
    return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  } catch {
    return '';
  }
}
