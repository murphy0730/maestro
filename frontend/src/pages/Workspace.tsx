import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Layout } from '@/components/layout/Layout';
import { SessionSidebar } from '@/components/layout/SessionSidebar';
import { TopBar } from '@/components/layout/TopBar';
import { Composer } from '@/features/orchestrator/Composer';
import { ConversationPanel } from '@/features/orchestrator/ConversationPanel';
import { RunTrace, type TraceView } from '@/features/runtime/RunTrace';
import { SkillImportModal } from '@/features/orchestrator/skills/SkillImportModal';
import { SkillManagerModal } from '@/features/orchestrator/skills/SkillManagerModal';
import { SettingsModal } from '@/features/settings/SettingsModal';
import { createSession, deleteSession, getSessionMessages, listSessions, renameSession, trustSkill, useSkills, type SessionMessage, type SessionSummary } from '@/api';
import { useRunStream } from '@/api/useRunStream';
import { useRunStore } from '@/stores/runStore';
import { useThemeStore } from '@/stores/themeStore';
import { useUiPreferencesStore, type RunMode } from '@/stores/uiPreferencesStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import type { SkillMeta } from '@/types';

export function Workspace() {
  const [clock, setClock] = useState('--:--:--');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string>();
  const [selectedSkills, setSelectedSkills] = useState<SkillMeta[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string>();
  const [importOpen, setImportOpen] = useState(false);
  const [skillManagerOpen, setSkillManagerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mode, setMode] = useState<RunMode>(() => useUiPreferencesStore.getState().defaultMode);
  const [traceView, setTraceView] = useState<TraceView>(() => useUiPreferencesStore.getState().traceDefault);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const sessionLoadGeneration = useRef(0);
  const terminalRefreshRef = useRef<string>();

  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const sidebarCollapsed = useUiPreferencesStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useUiPreferencesStore((state) => state.setSidebarCollapsed);
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);
  const operatorName = usePersonalizationStore((state) => state.data.howToAddress.trim() || '本地操作员');
  const skillsQuery = useSkills();
  const projection = useRunStore((state) => ({ run: state.run, tokens: state.tokens, upgradeReason: state.upgradeReason, diagnostics: state.diagnostics, events: state.events, recovered: state.recovered }));
  const { start, approve, cancel, restore, reconnect, transport, error: transportError } = useRunStream(sessionId);

  const refreshSessions = useCallback(async () => {
    const result = await listSessions();
    setSessions(result);
    return result;
  }, []);

  useEffect(() => {
    let active = true;
    setSessionsLoading(true);
    void refreshSessions().then(async (result) => {
      if (!active) return;
      const savedSessionId = useSessionStore.getState().activeSessionId;
      const first = result.find((session) => session.session_id === savedSessionId) ?? result[0] ?? await createSession('新任务');
      if (!active) return;
      if (result.length === 0) setSessions([first]);
      setSessionId(first.session_id);
      setActiveSessionId(first.session_id);
    }).catch((cause) => active && setWorkspaceError(messageOf(cause, '无法加载会话'))).finally(() => active && setSessionsLoading(false));
    return () => { active = false; };
  }, [refreshSessions, setActiveSessionId]);

  useEffect(() => {
    if (!sessionId) return;
    const generation = ++sessionLoadGeneration.current;
    const aborter = new AbortController();
    setHistoryLoading(true); setWorkspaceError(undefined); setMessages([]); setActiveSessionId(sessionId);
    void Promise.all([listSessions(aborter.signal), getSessionMessages(sessionId, aborter.signal)]).then(([latestSessions, history]) => {
      if (aborter.signal.aborted || generation !== sessionLoadGeneration.current) return;
      setSessions(latestSessions); setMessages(history);
      return restore(latestSessions.find((item) => item.session_id === sessionId)?.active_run_id);
    }).catch((cause) => { if (!aborter.signal.aborted && generation === sessionLoadGeneration.current) setWorkspaceError(messageOf(cause, '会话加载失败')); }).finally(() => { if (!aborter.signal.aborted && generation === sessionLoadGeneration.current) setHistoryLoading(false); });
    return () => aborter.abort();
  }, [historyReloadKey, restore, sessionId, setActiveSessionId]);

  useEffect(() => {
    const status = projection.run?.status;
    if (!projection.run || !['completed', 'failed', 'cancelled'].includes(status ?? '') || terminalRefreshRef.current === projection.run.run_id) return;
    terminalRefreshRef.current = projection.run.run_id;
    void getSessionMessages(sessionId).then(setMessages).catch(() => undefined);
    void refreshSessions().catch(() => undefined);
  }, [projection.run, refreshSessions, sessionId]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB'));
    tick(); const id = window.setInterval(tick, 1000); return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const collapseForWidth = () => { if (window.innerWidth < 1180) setSidebarCollapsed(true); };
    collapseForWidth(); window.addEventListener('resize', collapseForWidth); return () => window.removeEventListener('resize', collapseForWidth);
  }, [setSidebarCollapsed]);

  const currentSession = useMemo(() => sessions.find((session) => session.session_id === sessionId), [sessions, sessionId]);
  const availableSkills = skillsQuery.data?.skills ?? [];

  const createNewSession = async () => {
    setWorkspaceError(undefined);
    try { const created = await createSession('新任务'); setSessions((items) => [created, ...items]); setMode(useUiPreferencesStore.getState().defaultMode); setSessionId(created.session_id); }
    catch (cause) { setWorkspaceError(messageOf(cause, '新建会话失败')); }
  };
  const rename = async (id: string, title: string) => {
    try { const updated = await renameSession(id, title); setSessions((items) => items.map((item) => item.session_id === id ? updated : item)); }
    catch (cause) { setWorkspaceError(messageOf(cause, '重命名失败')); }
  };
  const remove = async (id: string) => {
    const target = sessions.find((item) => item.session_id === id);
    if (!target || !window.confirm(`确定删除会话“${target.title}”？此操作会删除其历史消息。`)) return;
    try {
      await deleteSession(id);
      const remaining = sessions.filter((item) => item.session_id !== id);
      setSessions(remaining);
      if (id === sessionId) {
        const next = remaining[0] ?? await createSession('新任务');
        if (remaining.length === 0) setSessions([next]);
        setSessionId(next.session_id);
      }
    } catch (cause) { setWorkspaceError(messageOf(cause, '删除会话失败')); }
  };
  const send = async (message: string, files: File[]) => {
    setWorkspaceError(undefined);
    try {
      const baseSkillNames = selectedSkills.map((skill) => skill.name);
      const skillNames = mode === 'scheduling'
        ? Array.from(new Set([...baseSkillNames, 'scheduling-query']))
        : baseSkillNames;
      const run = await start(message, files, skillNames);
      setMessages((current) => [...current, { role: 'user', content: message, ts: new Date().toISOString(), artifact_ids: run.input_artifact_ids ?? [], skill_names: skillNames, run_id: run.run_id }]);
      void refreshSessions().catch(() => undefined);
    } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) { setWorkspaceError(`${messageOf(cause, '任务发送失败')}；草稿与附件已保留，可重新发送`); throw cause; } }
  };

  return <>
    <SkillImportModal open={importOpen} onClose={() => setImportOpen(false)} onImported={() => { void skillsQuery.refetch(); }} />
    <SkillManagerModal open={skillManagerOpen} onClose={() => setSkillManagerOpen(false)} skills={availableSkills} loading={skillsQuery.isLoading} onImport={() => setImportOpen(true)} onChanged={() => { void skillsQuery.refetch().then((result) => setSelectedSkills((selected) => selected.filter((item) => (result.data?.skills ?? []).some((skill) => skill.name === item.name)))); }} />
    <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    <Layout
      sidebar={<SessionSidebar sessions={sessions} activeSessionId={sessionId} collapsed={sidebarCollapsed} theme={theme} operatorName={operatorName} loading={sessionsLoading} onCollapsedChange={setSidebarCollapsed} onCreate={() => { void createNewSession(); }} onSelect={setSessionId} onRename={(id, title) => { void rename(id, title); }} onDelete={(id) => { void remove(id); }} onOpenSkills={() => setSkillManagerOpen(true)} onOpenSettings={() => setSettingsOpen(true)} onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')} />}
      topBar={<TopBar session={currentSession?.title ?? '新任务'} mode={mode} connection={transport} clock={clock} traceView={traceView} hasRun={Boolean(projection.run)} runStatus={projection.run?.status} onTraceViewChange={setTraceView} />}
      conversation={<div className="relative flex min-h-0 flex-1"><section className="flex min-w-0 flex-1 flex-col"><ConversationPanel messages={messages} projection={projection} loading={historyLoading} streaming={transport === 'connecting' || transport === 'streaming'} operatorName={operatorName} error={workspaceError ?? transportError} onRetry={transport === 'error' ? (projection.run ? () => { void reconnect(); } : undefined) : (sessionId ? () => setHistoryReloadKey((key) => key + 1) : undefined)} onSuggestion={(text) => { if (mode === 'auto' || mode === 'scheduling') void send(text, []); else setWorkspaceError('当前后端暂不支持该模式；请切回“自动”或“调度”后发送。'); }} /><Composer onSend={send} disabled={!sessionId || historyLoading || transport === 'uploading'} isStreaming={transport === 'connecting' || transport === 'streaming'} onStop={() => { void cancel().catch((cause) => setWorkspaceError(messageOf(cause, '停止运行失败'))); }} skills={availableSkills} selectedSkills={selectedSkills} onToggleSkill={(skill) => setSelectedSkills((current) => current.some((item) => item.name === skill.name) ? current.filter((item) => item.name !== skill.name) : [...current, skill])} onClearSkills={() => setSelectedSkills([])} onImportSkill={() => setImportOpen(true)} onTrustSkill={(skill) => { void trustSkill(skill.name, true).then(() => skillsQuery.refetch()).catch((cause) => setWorkspaceError(messageOf(cause, '技能信任失败'))); }} mode={mode} onModeChange={setMode} /></section><RunTrace projection={projection} view={traceView} onViewChange={setTraceView} approvingId={approvingId} approvalError={approvalError} onApprove={(approvalView, approved) => { setApprovingId(approvalView.approval_id); setApprovalError(undefined); void approve(approvalView.approval_id, approved, approvalView.run_revision).catch((cause) => setApprovalError(messageOf(cause, '审批提交失败；可能已过期或 revision 冲突'))).finally(() => setApprovingId(null)); }} /></div>}
    />
  </>;
}

function messageOf(cause: unknown, fallback: string) { return cause instanceof Error && cause.message ? cause.message : fallback; }
