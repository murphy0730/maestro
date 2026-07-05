import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ChatMessageData, ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { Layout } from '@/components/layout/Layout';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ContextPanelHost } from '@/components/ContextPanelHost';
import { Thread } from '@/features/orchestrator/Thread';
import { Composer } from '@/features/orchestrator/Composer';
import { SkillImportModal } from '@/features/orchestrator/skills/SkillImportModal';
import { useOrchestrator } from '@/features/orchestrator/useOrchestrator';
import { useConversationStore, useThemeStore } from '@/stores';
import { useSessionStore } from '@/stores/sessionStore';
import { useSessions, useCreateSession, useRenameSession, useDeleteSession, useSkills } from '@/api';
import { getSessionMessages } from '@/api/sessions';
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
  const activateEngine = useConversationStore((s) => s.activateEngine);
  const closeContextPanel = useConversationStore((s) => s.closeContextPanel);
  const resetThread = useConversationStore((s) => s.resetThread);

  // 服务器状态 (会话列表) 归 TanStack Query；本地只保留"当前选中哪个会话"
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActiveSessionId = useSessionStore((s) => s.setActiveSessionId);

  const sessionsQuery = useSessions();
  const sessionsData = sessionsQuery.data;
  const sessions = useMemo(() => sessionsData ?? [], [sessionsData]);
  const createSessionMut = useCreateSession();
  const renameSessionMut = useRenameSession();
  const deleteSessionMut = useDeleteSession();

  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  // 稳定的 fallback session ID（后端连接前短暂使用）
  const fallbackIdRef = useRef(crypto.randomUUID().replace(/-/g, ''));
  const currentSessionId = activeSessionId ?? fallbackIdRef.current;

  const { send, stop, selectClarification, confirmPending, liveMessage, isStreaming } =
    useOrchestrator(currentSessionId);

  const skillsQuery = useSkills();
  const skills = skillsQuery.data?.skills ?? [];

  const [route, setRoute] = useState<ComposerRoute>('auto');
  const [skill, setSkill] = useState<SkillMeta | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  /**
   * The query route and the RAG panel are strongly bound: selecting query
   * opens the knowledge-base manager on the right immediately; switching to
   * any other route closes it again. Other routes leave panel activation to
   * the streaming `context` event.
   *
   * Selecting a non-auto route also clears any active skill (mutual exclusion:
   * a forced engine and a skill cannot both win the route decision).
   */
  const handleRouteChange = (next: ComposerRoute) => {
    setRoute(next);
    if (next === 'query') activateEngine('query');
    else if (activeEngine === 'query') closeContextPanel();
    if (next !== 'auto') setSkill(null);
  };
  /** Selecting a skill forces the route back to auto (skill owns routing). */
  const handleSkillChange = (s: SkillMeta | null) => {
    setSkill(s);
    if (s) setRoute('auto');
  };
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
  const refetchSessions = sessionsQuery.refetch;
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      void refetchSessions();
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming, refetchSessions]);

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

  // 会话列表首次加载完成后初始化：选最近会话，无则自动新建。
  // 后端不可达 (query 不 success) 时保持欢迎消息。
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current || !sessionsQuery.isSuccess) return;
    initializedRef.current = true;
    const init = async () => {
      const fetched = sessionsQuery.data;
      if (fetched.length > 0) {
        const recent = fetched[0];
        setActiveSessionId(recent.session_id);
        await loadSession(recent.session_id);
      } else {
        try {
          const newSess = await createSessionMut.mutateAsync('新对话');
          setActiveSessionId(newSess.session_id);
          resetThread();
        } catch {
          // 新建失败：保持欢迎消息
        }
      }
    };
    void init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionsQuery.isSuccess]);

  /** 新建对话 */
  const handleNewConversation = useCallback(async () => {
    try {
      const newSess = await createSessionMut.mutateAsync('新对话');
      setActiveSessionId(newSess.session_id);
    } catch {
      // fallback: 只重置线程
    }
    resetThread();
  }, [createSessionMut, setActiveSessionId, resetThread]);

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
        await renameSessionMut.mutateAsync({ id, title });
      } catch {
        // 忽略重命名失败
      }
    },
    [renameSessionMut],
  );

  /** 删除会话；若删的是当前会话，切到剩余最近一条，无则新建 */
  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteSessionMut.mutateAsync(id); // 乐观移除，失败自动回滚
      } catch {
        return; // 删除失败：列表已回滚，当前会话不动
      }
      if (id !== activeSessionId) return;
      const remaining = sessions.filter((s) => s.session_id !== id);
      if (remaining.length > 0) {
        setActiveSessionId(remaining[0].session_id);
        await loadSession(remaining[0].session_id);
      } else {
        try {
          const newSess = await createSessionMut.mutateAsync('新对话');
          setActiveSessionId(newSess.session_id);
        } catch {
          setActiveSessionId(null);
        }
        resetThread();
      }
    },
    [
      activeSessionId,
      sessions,
      deleteSessionMut,
      createSessionMut,
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
  // 空会话（只有系统欢迎语）→ 输入框居中的开屏形态
  const isEmptyThread = thread.every((m) => m.kind === 'system');

  const composer = (
    <Composer
      onSend={(text) => send(text, route === 'auto' ? null : route, skill?.name ?? null)}
      route={route}
      mode={mode}
      onRouteChange={handleRouteChange}
      onModeChange={setMode}
      isStreaming={isStreaming}
      onStop={stop}
      skills={skills}
      skill={skill}
      onSkillChange={handleSkillChange}
      onImportSkill={() => setImportOpen(true)}
    />
  );

  return (
    <>
      <SkillImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(s) => {
          setSkill(s);
          setImportOpen(false);
        }}
      />
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
        isEmptyThread ? (
          /* 开屏形态：欢迎语 + 居中输入框；发出第一条消息后切回常规布局 */
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center pb-12">
            <div className="w-full max-w-[820px]">
              <div className="mb-5 text-center">
                <h1 className="text-h2 font-semibold tracking-tight text-text-primary">
                  您好，我是 Maestro
                </h1>
                <p className="mt-2 text-body text-text-secondary">
                  描述排产 / 调度 / 查询需求，或输入 / 使用斜杠命令
                </p>
              </div>
              {isLoading && (
                <div className="flex items-center justify-center pb-2 text-caption text-text-tertiary">
                  加载历史消息中…
                </div>
              )}
              {composer}
            </div>
          </div>
        ) : (
          <div className="relative flex min-h-0 flex-1 flex-col">
            <Thread
              messages={thread}
              author="周文涛"
              onClarifySelect={selectClarification}
              onActionConfirm={confirmPending}
            />
            {/* Composer floats over the thread so content scrolls under its glass */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0">
              {isLoading && (
                <div className="flex items-center justify-center py-2 text-caption text-text-tertiary">
                  加载历史消息中…
                </div>
              )}
              {composer}
            </div>
          </div>
        )
      }
      panel={
        panelOpen ? (
          <ContextPanelHost engine={activeEngine} onClose={closeContextPanel} />
        ) : undefined
      }
    />
    </>
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
