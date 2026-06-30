import { useEffect, useState } from 'react';
import type { ComposerMode, ComposerRoute } from '@/types';
import { Layout } from '@/components/layout/Layout';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ContextPanelHost } from '@/components/ContextPanelHost';
import { Thread } from '@/features/orchestrator/Thread';
import { Composer } from '@/features/orchestrator/Composer';
import { useOrchestrator } from '@/features/orchestrator/useOrchestrator';
import { useConversationStore } from '@/stores';
import { MOCK_SESSION, MOCK_CONVERSATIONS } from '@/mocks/session';

/**
 * Workspace — the live orchestrator surface. Conversation history, active
 * engine and panel state come from the zustand store; the streaming turn is
 * driven by useOrchestrator (→ useStreamingChat → /chat/stream via MSW).
 */
export function Workspace() {
  const messages = useConversationStore((s) => s.messages);
  const activeEngine = useConversationStore((s) => s.activeEngine);
  const contextPanelOpen = useConversationStore((s) => s.contextPanelOpen);
  const closeContextPanel = useConversationStore((s) => s.closeContextPanel);
  const resetThread = useConversationStore((s) => s.resetThread);

  const { send, selectClarification, liveMessage } = useOrchestrator();

  const [route, setRoute] = useState<ComposerRoute>('auto');
  const [mode, setMode] = useState<ComposerMode>('plan');
  const [clock, setClock] = useState('--:--:--');
  const [activeConversationId, setActiveConversationId] = useState(MOCK_CONVERSATIONS[0].id);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB'));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const thread = liveMessage ? [...messages, liveMessage] : messages;
  const panelOpen = contextPanelOpen && activeEngine !== null;

  return (
    <Layout
      sidebar={
        <Sidebar
          appName="Maestro"
          user={MOCK_SESSION.user}
          role={MOCK_SESSION.role}
          conversations={MOCK_CONVERSATIONS}
          activeId={activeConversationId}
          onSelect={setActiveConversationId}
          onNewConversation={resetThread}
        />
      }
      topBar={
        <TopBar
          session={MOCK_SESSION.title}
          engine={activeEngine}
          clock={clock}
          mesConnected={MOCK_SESSION.mesConnected}
        />
      }
      conversation={
        <>
          <Thread
            messages={thread}
            author={MOCK_SESSION.user}
            onClarifySelect={selectClarification}
          />
          <Composer
            onSend={(text) => send(text, activeEngine)}
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
