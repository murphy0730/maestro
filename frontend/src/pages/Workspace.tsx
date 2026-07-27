import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { SessionSidebar } from '@/components/layout/SessionSidebar';
import { TopBar } from '@/components/layout/TopBar';
import { Composer } from '@/features/orchestrator/Composer';
import { ConversationPanel } from '@/features/orchestrator/ConversationPanel';
import { RunTrace, type TraceView } from '@/features/runtime/RunTrace';
import { SettingsModal } from '@/features/settings/SettingsModal';
import { getSessionMessages, listSessions, trustSkill, useSkills, type SessionMessage } from '@/api';
import { useRunStream } from '@/api/useRunStream';
import { useWorkspaceSessions, messageOf } from '@/hooks/useWorkspaceSessions';
import { useRunStore } from '@/stores/runStore';
import { useThemeStore } from '@/stores/themeStore';
import { useUiPreferencesStore, type RunMode } from '@/stores/uiPreferencesStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import type { SkillMeta } from '@/types';

export function Workspace() {
  const navigate = useNavigate();
  const [clock, setClock] = useState('--:--:--');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<SkillMeta[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mode, setMode] = useState<RunMode>(() => useUiPreferencesStore.getState().defaultMode);
  const [traceView, setTraceView] = useState<TraceView>(
    () => useUiPreferencesStore.getState().traceDefault,
  );
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const sessionLoadGeneration = useRef(0);
  const terminalRefreshRef = useRef<string>();

  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const sidebarCollapsed = useUiPreferencesStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useUiPreferencesStore((state) => state.setSidebarCollapsed);
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);
  const operatorName = usePersonalizationStore(
    (state) => state.data.howToAddress.trim() || '周文涛',
  );
  const skillsQuery = useSkills();
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
  const projection = useRunStore((state) => ({
    run: state.run,
    tokens: state.tokens,
    upgradeReason: state.upgradeReason,
    diagnostics: state.diagnostics,
    events: state.events,
    recovered: state.recovered,
  }));
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
      !['completed', 'failed', 'cancelled'].includes(status ?? '') ||
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
    const skillNames =
      mode === 'scheduling'
        ? Array.from(new Set([...baseSkillNames, 'scheduling-query']))
        : baseSkillNames;
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
                onSuggestion={(text) => {
                  if (mode === 'auto' || mode === 'scheduling') void send(text, []);
                  else setWorkspaceError('当前后端暂不支持该模式；请切回“自动”或“调度”后发送。');
                }}
              />
              <Composer
                onSend={send}
                disabled={!sessionId || historyLoading || transport === 'uploading'}
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
              view={traceView}
              onViewChange={setTraceView}
              approvingId={approvingId}
              approvalError={approvalError}
              onApprove={(approvalView, approved) => {
                setApprovingId(approvalView.approval_id);
                setApprovalError(undefined);
                void approve(approvalView.approval_id, approved, approvalView.run_revision)
                  .catch((cause) =>
                    setApprovalError(messageOf(cause, '审批提交失败；可能已过期或 revision 冲突')),
                  )
                  .finally(() => setApprovingId(null));
              }}
            />
          </div>
        }
      />
    </>
  );
}
