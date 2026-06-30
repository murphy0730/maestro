import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { ChatMessageData, EngineType, IntentType, RouteEngine } from '@/types';
import { useStreamingChat } from '@/api';
import { ROUTE_META } from '@/lib/routes';
import { useConversationStore } from '@/stores';

const nowHM = () => new Date().toLocaleTimeString('en-GB').slice(0, 5);

/**
 * useOrchestrator — bridges the streaming chat API with the conversation store.
 *
 * The in-flight assistant turn lives in `useStreamingChat`; this hook renders
 * it as a live message and, on a terminal phase, commits a finalized message
 * to the store (agent reply, clarification card, or error) and activates the
 * engine carried by a `context` event. Clarification answers resume the stream.
 */
export function useOrchestrator() {
  const sessionIdRef = useRef<string>(crypto.randomUUID());
  const chat = useStreamingChat(sessionIdRef.current);
  const chatRef = useRef(chat);
  chatRef.current = chat;

  const addMessage = useConversationStore((s) => s.addMessage);
  const updateMessage = useConversationStore((s) => s.updateMessage);
  const activateEngine = useConversationStore((s) => s.activateEngine);

  // One assistant turn in flight: its id, start time, and a commit guard.
  const pendingRef = useRef(false);
  const turnIdRef = useRef<string>('');
  const turnTimeRef = useRef<string>('');

  // Commit the finalized turn when the stream reaches a terminal phase.
  useEffect(() => {
    if (!pendingRef.current) return;
    const c = chatRef.current;

    if (c.phase === 'done') {
      const engine = c.context?.engine ?? null;
      addMessage({
        id: turnIdRef.current,
        kind: 'agent',
        time: turnTimeRef.current,
        route: c.route?.intent,
        confidence: c.route?.confidence,
        reason: c.route?.reason,
        text: c.text || undefined,
        handoff: !!c.context,
      });
      if (engine) activateEngine(engine);
      pendingRef.current = false;
      c.reset();
    } else if (c.phase === 'awaiting_clarification' && c.clarify) {
      addMessage({
        id: turnIdRef.current,
        kind: 'clarify',
        time: turnTimeRef.current,
        confidence: c.route?.confidence ?? 0,
        reason: c.route?.reason ?? '',
        question: c.clarify.question,
        options: c.clarify.options.map((o) => ({ id: o.id, label: o.label, route: o.route_to })),
      });
      pendingRef.current = false;
      c.reset();
    } else if (c.phase === 'error') {
      addMessage({
        id: `err-${Date.now()}`,
        kind: 'system',
        text: `出错：${c.error?.message ?? '未知错误'}`,
      });
      pendingRef.current = false;
      c.reset();
    }
  }, [chat.phase, addMessage, activateEngine]);

  /** Send a user message; `currentEngine` carries session stickiness. */
  const send = useCallback(
    (text: string, currentEngine: EngineType | null) => {
      turnIdRef.current = `a-${Date.now()}`;
      turnTimeRef.current = nowHM();
      pendingRef.current = true;
      addMessage({ id: `u-${Date.now()}`, kind: 'user', time: nowHM(), text });
      chatRef.current.send(text, currentEngine);
    },
    [addMessage],
  );

  /** Answer a clarification: record the choice, then resume the stream. */
  const selectClarification = useCallback(
    (messageId: string, optionId: string, routeTo: IntentType) => {
      updateMessage(messageId, { selectedOptionId: optionId });
      const zh = routeTo === 'uncertain' ? '澄清' : ROUTE_META[routeTo].zh;
      addMessage({ id: `sys-${Date.now()}`, kind: 'system', time: nowHM(), text: `已选择 · 路由至 ${zh}引擎` });
      turnIdRef.current = `a-${Date.now()}`;
      turnTimeRef.current = nowHM();
      pendingRef.current = true;
      chatRef.current.selectClarification(optionId, routeTo);
    },
    [updateMessage, addMessage],
  );

  // The live assistant bubble while the stream is active (before commit).
  const liveMessage = useMemo<ChatMessageData | null>(() => {
    if (chat.phase !== 'streaming') return null;
    return {
      id: turnIdRef.current || 'live',
      kind: 'agent',
      time: turnTimeRef.current,
      route: chat.route?.intent as RouteEngine | undefined,
      confidence: chat.route?.confidence,
      reason: chat.route?.reason,
      text: chat.text || undefined,
      streaming: true,
    };
  }, [chat.phase, chat.route, chat.text]);

  return { send, selectClarification, liveMessage, isStreaming: chat.phase === 'streaming' };
}
