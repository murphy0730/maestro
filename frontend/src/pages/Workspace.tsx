import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { SessionSidebar } from '@/components/layout/SessionSidebar';
import { TopBar } from '@/components/layout/TopBar';
import { Composer } from '@/features/orchestrator/Composer';
import { ConversationPanel } from '@/features/orchestrator/ConversationPanel';
import { RunTrace, type TraceView } from '@/features/runtime/RunTrace';
import { useCapabilityDirectory } from '@/features/runtime/capabilityLabel';
import { SettingsModal } from '@/features/settings/SettingsModal';
import {
  deleteSessionMessage,
  getSessionMessages,
  listSessions,
  trustSkill,
  useSkills,
  type SessionMessage,
} from '@/api';
import { useRunStream } from '@/api/useRunStream';
import { useWorkspaceSessions, messageOf } from '@/hooks/useWorkspaceSessions';
import { TERMINAL_RUN_STATUSES, useRunStore } from '@/stores/runStore';
import { useThemeStore } from '@/stores/themeStore';
import { useUiPreferencesStore, type RunMode } from '@/stores/uiPreferencesStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import type { SkillMeta } from '@/types';

const WHATIF_REQUEST =
  /(如果|假如|假设|推演|what[- ]?if|改成|调整|增加|减少|新增|删除|停机|不上班|只上|加班|扩产)/i;

export function Workspace() {
  const navigate = useNavigate();
  const [clock, setClock] = useState('--:--:--');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<SkillMeta[]>([]);
  const [approvalError, setApprovalError] = useState<string>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mode, setMode] = useState<RunMode>(() => useUiPreferencesStore.getState().defaultMode);
  const [traceView, setTraceView] = useState<TraceView>(
    () => useUiPreferencesStore.getState().traceDefault,
  );
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const activeSessionIdRef = useRef('');
  const sessionLoadGeneration = useRef(0);
  const messageDeletionPending = useRef(false);
  const terminalRefreshRef = useRef<string>();
  const revealedApprovalRef = useRef<string>();

  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const sidebarCollapsed = useUiPreferencesStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useUiPreferencesStore((state) => state.setSidebarCollapsed);
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);
  const operatorName = usePersonalizationStore(
    (state) => state.data.howToAddress.trim() || '周文涛',
  );
  const skillsQuery = useSkills();
  // 能力目录只在这里取一次，运行轨迹与对话流共用同一份翻译。
  const describeCapability = useCapabilityDirectory();
  const {
    sessions,
    setSessions,
    sessionId,
    setSessionId,
    loading: sessionsLoading,
    error: workspaceError,
    setError: setWorkspaceError,
    refresh: refreshSessions,
    create: createNewSession,
    rename,
    remove,
  } = useWorkspaceSessions();
  activeSessionIdRef.current = sessionId;
  const projection = useRunStore((state) => ({
    run: state.run,
    tokens: state.tokens,
    upgradeReason: state.upgradeReason,
    diagnostics: state.diagnostics,
    events: state.events,
    recovered: state.recovered,
    resuming: state.resuming,
  }));
  const pendingApprovalId =
    projection.run?.status === 'waiting_approval'
      ? projection.run.pending_approvals.find(
          (approval) =>
            approval.status === 'pending' &&
            approval.approval_id !== projection.resuming?.approvalId,
        )?.approval_id
      : undefined;
  const resetRun = useRunStore((state) => state.reset);
  const {
    start,
    approve,
    cancel,
    restore,
    reconnect,
    transport,
    error: transportError,
  } = useRunStream(sessionId);

  useEffect(() => {
    if (!projection.run || !pendingApprovalId) return;
    const approvalKey = `${projection.run.run_id}:${pendingApprovalId}`;
    if (revealedApprovalRef.current === approvalKey) return;
    revealedApprovalRef.current = approvalKey;
    setTraceView((current) => (current === 'hidden' ? 'docked' : current));
  }, [pendingApprovalId, projection.run]);

  useEffect(() => {
    if (!sessionId) return;
    const generation = ++sessionLoadGeneration.current;
    const aborter = new AbortController();
    setHistoryLoading(true);
    setWorkspaceError(undefined);
    setMessages([]);
    setActiveSessionId(sessionId);
    void Promise.all([listSessions(aborter.signal), getSessionMessages(sessionId, aborter.signal)])
      .then(([latestSessions, history]) => {
        if (aborter.signal.aborted || generation !== sessionLoadGeneration.current) return;
        setSessions(latestSessions);
        setMessages(history);
        return restore(latestSessions.find((item) => item.session_id === sessionId)?.active_run_id);
      })
      .catch((cause) => {
        if (!aborter.signal.aborted && generation === sessionLoadGeneration.current)
          setWorkspaceError(messageOf(cause, '会话加载失败'));
      })
      .finally(() => {
        if (!aborter.signal.aborted && generation === sessionLoadGeneration.current)
          setHistoryLoading(false);
      });
    return () => aborter.abort();
  }, [historyReloadKey, restore, sessionId, setActiveSessionId, setSessions, setWorkspaceError]);

  useEffect(() => {
    const status = projection.run?.status;
    if (
      !projection.run ||
      !status ||
      !TERMINAL_RUN_STATUSES.has(status) ||
      terminalRefreshRef.current === projection.run.run_id
    )
      return;
    terminalRefreshRef.current = projection.run.run_id;
    void getSessionMessages(sessionId)
      .then(setMessages)
      .catch(() => undefined);
    void refreshSessions().catch(() => undefined);
  }, [projection.run, refreshSessions, sessionId]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB'));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const collapseForWidth = () => {
      if (window.innerWidth < 1180) setSidebarCollapsed(true);
    };
    collapseForWidth();
    window.addEventListener('resize', collapseForWidth);
    return () => window.removeEventListener('resize', collapseForWidth);
  }, [setSidebarCollapsed]);

  const currentSession = useMemo(
    () => sessions.find((session) => session.session_id === sessionId),
    [sessions, sessionId],
  );
  const availableSkills = skillsQuery.data?.skills ?? [];

  const send = async (message: string, files: File[]) => {
    setWorkspaceError(undefined);
    const baseSkillNames = selectedSkills.map((skill) => skill.name);
    const automaticSkill = WHATIF_REQUEST.test(message)
      ? 'whatif-planning'
      : mode === 'scheduling'
        ? 'scheduling-query'
        : undefined;
    const skillNames =
      automaticSkill === undefined
        ? baseSkillNames
        : Array.from(new Set([...baseSkillNames, automaticSkill]));
    const optimisticMessage: SessionMessage = {
      role: 'user',
      content: message,
      ts: new Date().toISOString(),
      artifact_ids: [],
      skill_names: skillNames,
    };
    setMessages((current) => [...current, optimisticMessage]);
    try {
      const run = await start(message, files, skillNames);
      setMessages((current) =>
        current.map((item) =>
          item === optimisticMessage
            ? {
                ...item,
                artifact_ids: run.input_artifact_ids ?? [],
                run_id: run.run_id,
              }
            : item,
        ),
      );
      void refreshSessions().catch(() => undefined);
    } catch (cause) {
      setMessages((current) => current.filter((item) => item !== optimisticMessage));
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setWorkspaceError(`${messageOf(cause, '任务发送失败')}；草稿与附件已保留，可重新发送`);
        throw cause;
      }
    }
  };

  const deleteMessage = async (messageId: string, cascade: boolean) => {
    if (messageDeletionPending.current) return;
    // 菜单打开后 Run 状态还会变，所以这里再拦一道：删掉一个还在跑的回合的提问，
    // 后端不会因此停下，最后落回来的就是一条没有问题的回答。
    const target = messages.find((item) => item.id === messageId);
    const activeRun = projection.run;
    if (
      activeRun &&
      !TERMINAL_RUN_STATUSES.has(activeRun.status) &&
      target?.run_id === activeRun.run_id
    ) {
      setWorkspaceError('运行进行中，请先停止再删除该消息');
      return;
    }
    const deletingSessionId = sessionId;
    const generation = sessionLoadGeneration.current;
    messageDeletionPending.current = true;
    setWorkspaceError(undefined);
    try {
      // 以服务端回报的 deleted_ids 为准：级联时被删的不止点中的那一条。
      const { deleted_ids: deletedIds } = await deleteSessionMessage(sessionId, messageId, cascade);
      const removed = new Set(deletedIds);
      if (
        deletingSessionId === activeSessionIdRef.current &&
        generation === sessionLoadGeneration.current
      ) {
        const droppedActiveRun = messages.some(
          (item) => item.id && removed.has(item.id) && item.run_id === projection.run?.run_id,
        );
        setMessages((current) => current.filter((item) => !(item.id && removed.has(item.id))));
        if (droppedActiveRun) resetRun();
      }
      void refreshSessions().catch(() => undefined);
    } catch (cause) {
      if (
        deletingSessionId === activeSessionIdRef.current &&
        generation === sessionLoadGeneration.current
      ) {
        void getSessionMessages(sessionId)
          .then(setMessages)
          .catch(() => undefined);
        setWorkspaceError(messageOf(cause, '消息删除失败'));
      }
    } finally {
      messageDeletionPending.current = false;
    }
  };

  return (
    <>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <Layout
        sidebar={
          <SessionSidebar
            sessions={sessions}
            activeSessionId={sessionId}
            collapsed={sidebarCollapsed}
            theme={theme}
            operatorName={operatorName}
            loading={sessionsLoading}
            onCollapsedChange={setSidebarCollapsed}
            onCreate={() => {
              void createNewSession().then((created) => {
                if (created) setMode(useUiPreferencesStore.getState().defaultMode);
              });
            }}
            onSelect={setSessionId}
            onRename={(id, title) => {
              void rename(id, title);
            }}
            onDelete={(id) => {
              void remove(id);
            }}
            onOpenSkills={() => navigate('/settings/skills')}
            onOpenSettings={() => setSettingsOpen(true)}
            onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          />
        }
        topBar={
          <TopBar
            session={currentSession?.title ?? '新任务'}
            mode={mode}
            connection={transport}
            clock={clock}
            traceView={traceView}
            hasRun={Boolean(projection.run)}
            runStatus={projection.run?.status}
            onTraceViewChange={setTraceView}
          />
        }
        conversation={
          <div className="relative flex min-h-0 flex-1">
            <section className="flex min-w-0 flex-1 flex-col">
              <ConversationPanel
                messages={messages}
                projection={projection}
                describe={describeCapability}
                loading={historyLoading}
                streaming={transport === 'connecting' || transport === 'streaming'}
                operatorName={operatorName}
                error={workspaceError ?? transportError}
                onRetry={
                  transport === 'error'
                    ? projection.run
                      ? () => {
                          void reconnect();
                        }
                      : undefined
                    : sessionId
                      ? () => setHistoryReloadKey((key) => key + 1)
                      : undefined
                }
                onDeleteMessage={(messageId, cascade) => {
                  void deleteMessage(messageId, cascade);
                }}
                onSuggestion={(text) => {
                  if (mode === 'auto' || mode === 'scheduling') void send(text, []);
                  else setWorkspaceError('当前后端暂不支持该模式；请切回“自动”或“调度”后发送。');
                }}
              />
              <Composer
                onSend={send}
                disabled={
                  !sessionId || historyLoading || transport === 'uploading' || !!projection.resuming
                }
                isStreaming={transport === 'connecting' || transport === 'streaming'}
                onStop={() => {
                  void cancel().catch((cause) =>
                    setWorkspaceError(messageOf(cause, '停止运行失败')),
                  );
                }}
                skills={availableSkills}
                selectedSkills={selectedSkills}
                onToggleSkill={(skill) =>
                  setSelectedSkills((current) =>
                    current.some((item) => item.name === skill.name)
                      ? current.filter((item) => item.name !== skill.name)
                      : [...current, skill],
                  )
                }
                onClearSkills={() => setSelectedSkills([])}
                onImportSkill={() => navigate('/settings/skills?import=1')}
                onTrustSkill={(skill) => {
                  void trustSkill(skill.name, true)
                    .then(() => skillsQuery.refetch())
                    .catch((cause) => setWorkspaceError(messageOf(cause, '技能信任失败')));
                }}
                mode={mode}
                onModeChange={setMode}
              />
            </section>
            <RunTrace
              projection={projection}
              describe={describeCapability}
              view={traceView}
              onViewChange={setTraceView}
              approvalError={approvalError}
              onApprove={(approvalView, approved) => {
                setApprovalError(undefined);
                void approve(approvalView.approval_id, approved, approvalView.run_revision).catch(
                  (cause) =>
                    setApprovalError(messageOf(cause, '审批提交失败；可能已过期或 revision 冲突')),
                );
              }}
            />
          </div>
        }
      />
    </>
  );
}
