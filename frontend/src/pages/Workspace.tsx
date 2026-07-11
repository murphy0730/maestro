import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { Layout } from '@/components/layout/Layout';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ContextPanelHost } from '@/components/ContextPanelHost';
import { Thread } from '@/features/orchestrator/Thread';
import { Composer } from '@/features/orchestrator/Composer';
import { SkillImportModal } from '@/features/orchestrator/skills/SkillImportModal';
import { useOrchestrator } from '@/features/orchestrator/useOrchestrator';
import { useConversationStore, useDefaultEngineStore, useThemeStore } from '@/stores';
import { useSkills, useTrustSkill } from '@/api';
import { useWorkspaceSessions } from './workspace/useWorkspaceSessions';

export function Workspace() {
  const navigate = useNavigate();
  const messages = useConversationStore((state) => state.messages);
  const activeEngine = useConversationStore((state) => state.activeEngine);
  const schedulingSteps = useConversationStore((state) => state.schedulingSteps);
  const contextPanelOpen = useConversationStore((state) => state.contextPanelOpen);
  const activateEngine = useConversationStore((state) => state.activateEngine);
  const closeContextPanel = useConversationStore((state) => state.closeContextPanel);

  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const defaultEngine = useDefaultEngineStore((state) => state.defaultEngine);
  const setDefaultEngine = useDefaultEngineStore((state) => state.setDefaultEngine);

  const [route, setRoute] = useState<ComposerRoute>(defaultEngine);
  const [selectedSkills, setSelectedSkills] = useState<SkillMeta[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [mode, setMode] = useState<ComposerMode>('plan');
  const [clock, setClock] = useState('--:--:--');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const resetComposer = useCallback(() => {
    setRoute(defaultEngine);
    if (defaultEngine !== 'auto') setSelectedSkills([]);
  }, [defaultEngine]);

  const {
    activeSession,
    activeSessionId,
    currentSessionId,
    handleDeleteSession,
    handleNewConversation,
    handleRenameSession,
    handleSelectSession,
    isLoading,
    refetchSessions,
    sidebarConversations,
  } = useWorkspaceSessions({ onFreshConversation: resetComposer });
  const { send, stop, selectClarification, confirmPending, liveMessage, isStreaming } =
    useOrchestrator(currentSessionId);

  const skillsQuery = useSkills();
  const trustSkillMutation = useTrustSkill();
  const skills = skillsQuery.data?.skills ?? [];

  const handleRouteChange = (next: ComposerRoute) => {
    setRoute(next);
    if (next === 'query') activateEngine('query');
    else if (activeEngine === 'query') closeContextPanel();
    if (next !== 'auto') setSelectedSkills([]);
  };

  const handleToggleSkill = (skill: SkillMeta) => {
    setSelectedSkills((current) =>
      current.some((item) => item.name === skill.name)
        ? current.filter((item) => item.name !== skill.name)
        : [...current, skill],
    );
    setRoute('auto');
  };

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB'));
    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  const previousStreamingRef = useRef(false);
  useEffect(() => {
    if (previousStreamingRef.current && !isStreaming) {
      void refetchSessions();
    }
    previousStreamingRef.current = isStreaming;
  }, [isStreaming, refetchSessions]);

  const thread = liveMessage ? [...messages, liveMessage] : messages;
  const panelOpen = contextPanelOpen && activeEngine !== null;
  const isEmptyThread = thread.every((message) => message.kind === 'system');

  const composer = (
    <Composer
      onSend={(text, attachments) =>
        send(
          text,
          route === 'auto' ? null : route,
          selectedSkills.map((skill) => skill.name),
          mode,
          attachments,
        )
      }
      route={route}
      mode={mode}
      onRouteChange={handleRouteChange}
      onModeChange={setMode}
      isStreaming={isStreaming}
      onStop={stop}
      skills={skills}
      selectedSkills={selectedSkills}
      onToggleSkill={handleToggleSkill}
      onClearSkills={() => setSelectedSkills([])}
      onImportSkill={() => setImportOpen(true)}
      onTrustSkill={(skill) => {
        if (!skill.package_sha256) return;
        const accepted = window.confirm(
          `信任技能「${skill.display_name ?? skill.name}」当前版本？\n\n脚本每次执行仍会请求确认；SRT 不可用时，确认后可能在宿主机执行。\n\nHash: ${skill.package_sha256}`,
        );
        if (accepted) {
          void trustSkillMutation.mutateAsync({
            name: skill.name,
            packageSha256: skill.package_sha256,
          });
        }
      }}
    />
  );

  return (
    <>
      <SkillImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(skill) => {
          setSelectedSkills((current) =>
            current.some((item) => item.name === skill.name) ? current : [...current, skill],
          );
          setImportOpen(false);
        }}
      />
      <Layout
        sidebar={
          sidebarCollapsed ? null : (
            <Sidebar
              appName="Maestro"
              user="周文涛"
              initial="Z"
              role="排产调度员"
              conversations={sidebarConversations}
              activeId={activeSessionId ?? ''}
              onSelect={handleSelectSession}
              onNewConversation={handleNewConversation}
              onOpenTasks={() => navigate('/tasks')}
              onRenameSession={handleRenameSession}
              onDeleteSession={handleDeleteSession}
              onCollapse={() => setSidebarCollapsed(true)}
              theme={theme}
              onSetTheme={setTheme}
              defaultEngine={defaultEngine}
              onSetDefaultEngine={setDefaultEngine}
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
                onClarifySelect={(messageId, optionId, routeTo) =>
                  selectClarification(messageId, optionId, routeTo, mode)
                }
                onActionConfirm={confirmPending}
              />
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
            <ContextPanelHost
              engine={activeEngine}
              onClose={closeContextPanel}
              schedulingSteps={schedulingSteps}
            />
          ) : undefined
        }
      />
    </>
  );
}
