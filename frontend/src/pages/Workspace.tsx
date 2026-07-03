import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessageData, ComposerMode, ComposerRoute } from '@/types';
import { Layout } from '@/components/layout/Layout';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ContextPanelHost } from '@/components/ContextPanelHost';
import { Thread } from '@/features/orchestrator/Thread';
import { Composer } from '@/features/orchestrator/Composer';
import { useOrchestrator } from '@/features/orchestrator/useOrchestrator';
import { useConversationStore, useThemeStore } from '@/stores';
import { useSessionStore } from '@/stores/sessionStore';
import {
  listSessions,
  createSession,
  getSessionMessages,
  renameSession,
  deleteSession,
} from '@/api/sessions';
import type { ConversationSummary } from '@/mocks/session';
import type { RouteEngine } from '@/types';

/**
 * Workspace — 完整的 Agent 对话工作区。
 *
 * 会话管理逻辑:
 *  - 挂载时从后端拉取会话列表；若无会话则自动新建一条。
 *  - "新建对话"按钮 → POST /sessions → 切换到新会话。
 *  - 点击历史会话 → GET /sessions/{id}/messages → 恢复消息线程。
 *  - activeSessionId 驱动 useOrchestrator，确保消息发到正确会话。
 */
export function Workspace() {
  const messages = useConversationStore((s) => s.messages);
  const activeEngine = useConversationStore((s) => s.activeEngine);
  const contextPanelOpen = useConversationStore((s) => s.contextPanelOpen);
  const closeContextPanel = useConversationStore((s) => s.closeContextPanel);
  const resetThread = useConversationStore((s) => s.resetThread);

  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setSessions = useSessionStore((s) => s.setSessions);
  const upsertSession = useSessionStore((s) => s.upsertSession);
  const removeSession = useSessionStore((s) => s.removeSession);
  const setActiveSessionId = useSessionStore((s) => s.setActiveSessionId);

  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  // 稳定的 fallback session ID（后端连接前短暂使用）
  const fallbackIdRef = useRef(crypto.randomUUID().replace(/-/g, ''));
  const currentSessionId = activeSessionId ?? fallbackIdRef.current;

  const { send, selectClarification, liveMessage, isStreaming } = useOrchestrator(currentSessionId);

  const [route, setRoute] = useState<ComposerRoute>('auto');
  const [mode, setMode] = useState<ComposerMode>('plan');
  const [clock, setClock] = useState('--:--:--');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // 时钟
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB'));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  // 一轮流式对话结束后刷新会话列表，拿到后端生成的智能标题（及引擎/时间）
  const prevStreamingRef = useRef(false);
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      listSessions()
        .then(setSessions)
        .catch(() => {});
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, setSessions]);

  /** 把后端 StoredMessage 列表转为前端 ChatMessageData */
  const storedToThread = useCallback(
    (stored: Awaited<ReturnType<typeof getSessionMessages>>): ChatMessageData[] => {
      const initial: ChatMessageData = {
        id: 'sys-welcome',
        kind: 'system',
        text: '新会话 · 在下方描述排产 / 调度 / 查询需求开始',
      };
      if (stored.length === 0) return [initial];
      return [
        initial,
        ...stored.map((m, i) => ({
          id: `hist-${i}`,
          kind: m.role === 'user' ? ('user' as const) : ('agent' as const),
          text: m.content,
          time: m.ts ? new Date(m.ts).toLocaleTimeString('en-GB').slice(0, 5) : undefined,
        })),
      ];
    },
    [],
  );

  /** 加载会话消息并重置线程 */
  const loadSession = useCallback(
    async (sessionId: string) => {
      setIsLoading(true);
      try {
        const stored = await getSessionMessages(sessionId);
        resetThread(storedToThread(stored));
      } catch {
        resetThread();
      } finally {
        setIsLoading(false);
      }
    },
    [resetThread, storedToThread],
  );

  // 挂载时初始化会话列表
  useEffect(() => {
    const init = async () => {
      try {
        const fetched = await listSessions();
        setSessions(fetched);
        if (fetched.length > 0) {
          const recent = fetched[0];
          setActiveSessionId(recent.session_id);
          await loadSession(recent.session_id);
        } else {
          // 无会话 → 自动新建
          const newSess = await createSession('新对话');
          upsertSession(newSess);
          setActiveSessionId(newSess.session_id);
          resetThread();
        }
      } catch {
        // 后端不可达：保持欢迎消息
      }
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 新建对话 */
  const handleNewConversation = useCallback(async () => {
    try {
      const newSess = await createSession('新对话');
      upsertSession(newSess);
      setActiveSessionId(newSess.session_id);
      resetThread();
    } catch {
      // fallback: 只重置线程
      resetThread();
    }
  }, [upsertSession, setActiveSessionId, resetThread]);

  /** 切换历史会话 */
  const handleSelectSession = useCallback(
    async (id: string) => {
      if (id === activeSessionId) return;
      setActiveSessionId(id);
      await loadSession(id);
    },
    [activeSessionId, setActiveSessionId, loadSession],
  );

  /** 重命名会话 */
  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      try {
        const updated = await renameSession(id, title);
        upsertSession(updated);
      } catch {
        // 忽略重命名失败
      }
    },
    [upsertSession],
  );

  /** 删除会话；若删的是当前会话，切到剩余最近一条，无则新建 */
  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteSession(id);
      } catch {
        // 后端删除失败仍从本地移除，避免残留
      }
      removeSession(id);
      if (id !== activeSessionId) return;
      const remaining = sessions.filter((s) => s.session_id !== id);
      if (remaining.length > 0) {
        setActiveSessionId(remaining[0].session_id);
        await loadSession(remaining[0].session_id);
      } else {
        try {
          const newSess = await createSession('新对话');
          upsertSession(newSess);
          setActiveSessionId(newSess.session_id);
          resetThread();
        } catch {
          setActiveSessionId(null);
          resetThread();
        }
      }
    },
    [
      activeSessionId,
      sessions,
      removeSession,
      upsertSession,
      setActiveSessionId,
      loadSession,
      resetThread,
    ],
  );

  // 把 SessionInfo 转为 Sidebar 所需的 ConversationSummary
  const sidebarConversations: ConversationSummary[] = sessions.map((s) => ({
    id: s.session_id,
    title: s.title,
    engine: (s.engine as RouteEngine | null) ?? null,
    time: formatRelativeTime(s.updated_at),
  }));

  const thread = liveMessage ? [...messages, liveMessage] : messages;
  const panelOpen = contextPanelOpen && activeEngine !== null;
  const activeSession = sessions.find((s) => s.session_id === activeSessionId);

  return (
    <Layout
      sidebar={
        sidebarCollapsed ? null : (
          <Sidebar
            appName="Maestro"
            user="周文涛"
            role="排产调度员"
            conversations={sidebarConversations}
            activeId={activeSessionId ?? ''}
            onSelect={handleSelectSession}
            onNewConversation={handleNewConversation}
            onRenameSession={handleRenameSession}
            onDeleteSession={handleDeleteSession}
            onCollapse={() => setSidebarCollapsed(true)}
            theme={theme}
            onSetTheme={setTheme}
          />
        )
      }
      topBar={
        <TopBar
          session={activeSession?.title ?? '新对话'}
          engine={activeEngine}
          clock={clock}
          mesConnected
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed(false)}
        />
      }
      conversation={
        <>
          <Thread messages={thread} author="周文涛" onClarifySelect={selectClarification} />
          {isLoading && (
            <div className="flex items-center justify-center py-4 text-caption text-text-tertiary">
              加载历史消息中…
            </div>
          )}
          <Composer
            onSend={(text) => send(text, route === 'auto' ? null : route)}
            route={route}
            mode={mode}
            onRouteChange={setRoute}
            onModeChange={setMode}
          />
        </>
      }
      panel={
        panelOpen ? (
          <ContextPanelHost engine={activeEngine} onClose={closeContextPanel} />
        ) : undefined
      }
    />
  );
}

/** 把 ISO 时间戳转为相对可读时间（刚刚 / 今天 HH:mm / 昨天 / 日期）*/
function formatRelativeTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 2) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const isSameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (isSameDay) return d.toLocaleTimeString('en-GB').slice(0, 5);
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday =
      d.getFullYear() === yesterday.getFullYear() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getDate() === yesterday.getDate();
    if (isYesterday) return '昨天';
    return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  } catch {
    return '';
  }
}
