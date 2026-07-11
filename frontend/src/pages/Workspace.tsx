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
import { Modal } from '@/components/ui/Modal';
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

  const [route, setRoute] = useState<ComposerRoute>('auto');
  const [selectedSkills, setSelectedSkills] = useState<SkillMeta[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [mode, setMode] = useState<ComposerMode>('plan');
  const [clock, setClock] = useState('--:--:--');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [skillAwaitingTrust, setSkillAwaitingTrust] = useState<SkillMeta | null>(null);

  const resetComposer = useCallback(() => {
    setRoute('auto');
    setSelectedSkills([]);
  }, []);

  const {
    activeSession,
    activeSessionId,
    currentSessionId,
    handleDeleteSession,
    handleNewConversation,
    handleRenameSession,
    handleSelectSession,
    isLoading,
    isSessionReady,
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
          // A selected skill owns this turn. Never leak a sticky/default engine
          // into the request, even if the route state has not rendered "auto" yet.
          selectedSkills.length > 0 || route === 'auto' ? null : route,
          selectedSkills.map((skill) => skill.name),
          mode,
          attachments,
        )
      }
      route={route}
      mode={mode}
      disabled={!isSessionReady}
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
        setSkillAwaitingTrust(skill);
      }}
    />
  );

  return (
    <>
      <Modal
        open={skillAwaitingTrust !== null}
        onClose={() => setSkillAwaitingTrust(null)}
        title="信任这个技能版本？"
        subtitle="信任仅适用于当前文件版本；脚本每次执行仍会单独请求授权。"
        widthClassName="max-w-[520px]"
        footer={
          <div className="flex w-full justify-end gap-2">
            <button
              type="button"
              onClick={() => setSkillAwaitingTrust(null)}
              className="h-control rounded-sm px-4 text-body-sm font-medium text-text-secondary hover:bg-surface-3"
            >
              取消
            </button>
            <button
              type="button"
              disabled={trustSkillMutation.isPending}
              onClick={() => {
                if (!skillAwaitingTrust?.package_sha256) return;
                void trustSkillMutation
                  .mutateAsync({
                    name: skillAwaitingTrust.name,
                    packageSha256: skillAwaitingTrust.package_sha256,
                  })
                  .then(() => setSkillAwaitingTrust(null));
              }}
              className="h-control rounded-sm bg-auth-confirm px-4 text-body-sm font-semibold text-white disabled:opacity-50"
            >
              {trustSkillMutation.isPending ? '正在处理…' : '确认信任'}
            </button>
          </div>
        }
      >
        {skillAwaitingTrust && (
          <div className="space-y-3 text-body text-text-secondary">
            <p className="m-0 text-text-primary">
              {skillAwaitingTrust.display_name ?? skillAwaitingTrust.name}
            </p>
            <p className="m-0 leading-relaxed">
              SRT 不可用时，获准执行的脚本可能在宿主机运行。请仅信任来源可靠且内容已审查的技能。
            </p>
            <p className="m-0 break-all font-mono text-micro text-text-tertiary">
              SHA-256 · {skillAwaitingTrust.package_sha256}
            </p>
          </div>
        )}
      </Modal>
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
              onSelect={(id) => {
                resetComposer();
                void handleSelectSession(id);
              }}
              onNewConversation={handleNewConversation}
              onOpenTasks={() => navigate('/tasks')}
              onOpenSkills={() => navigate('/settings/skills')}
              onOpenConnectors={() => navigate('/settings/connectors')}
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
                userAvatar="Z"
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
