import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  ApiErrorBody,
  ChatContextEvent,
  ChatStreamEvent,
  ClarifyPayload,
  ComposerMode,
  EngineType,
  IntentType,
  PendingActionPayload,
  RouteDecision,
} from '@/types';
import { ApiError } from './client';
import { streamChat, clarifyChat } from './chat';

export type StreamPhase = 'idle' | 'streaming' | 'awaiting_clarification' | 'done' | 'error';

export interface StreamingChatState {
  phase: StreamPhase;
  /** Route decision, available as soon as the `route` event arrives. */
  route: RouteDecision | null;
  /** Assistant text accumulated from `token` deltas. */
  text: string;
  /** Clarification card when intent = uncertain. */
  clarify: ClarifyPayload | null;
  /** Latest Context Panel activation/update. */
  context: ChatContextEvent | null;
  /** Latest execution progress line (from real-time `progress` events). */
  progress: string | null;
  /** All progress/thinking lines of this turn, in arrival order. */
  progressLog: string[];
  /** Write actions awaiting human confirmation (from the `actions` event). */
  actions: PendingActionPayload[];
  /** Final message id from the `done` event. */
  messageId: string | null;
  error: ApiErrorBody | null;
}

const INITIAL: StreamingChatState = {
  phase: 'idle',
  route: null,
  text: '',
  clarify: null,
  context: null,
  progress: null,
  progressLog: [],
  actions: [],
  messageId: null,
  error: null,
};

/**
 * useStreamingChat — drives the orchestrator's `POST /chat/stream` (and the
 * clarify follow-up) and surfaces the SSE stream as incrementally-updating
 * React state: route decision first, then streamed `token` text, plus
 * clarify / context / done. Pure data layer — no UI here.
 *
 * A new `send`/`selectClarification` aborts any in-flight stream. The stream
 * is also aborted on unmount.
 */
export function useStreamingChat(sessionId: string) {
  const [state, setState] = useState<StreamingChatState>(INITIAL);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const consume = useCallback(async (gen: AsyncGenerator<ChatStreamEvent>) => {
    try {
      for await (const evt of gen) {
        if (!mountedRef.current) return;
        switch (evt.event) {
          case 'route':
            setState((s) => ({ ...s, route: evt.data, phase: 'streaming' }));
            break;
          case 'token':
            setState((s) => ({ ...s, text: s.text + evt.data.delta }));
            break;
          case 'clarify':
            setState((s) => ({ ...s, clarify: evt.data, phase: 'awaiting_clarification' }));
            break;
          case 'context':
            setState((s) => ({ ...s, context: evt.data }));
            break;
          case 'progress':
            setState((s) => ({
              ...s,
              progress: evt.data.text,
              progressLog: [...s.progressLog, evt.data.text],
            }));
            break;
          case 'actions':
            setState((s) => ({ ...s, actions: evt.data.actions }));
            break;
          case 'done':
            setState((s) => ({
              ...s,
              messageId: evt.data.message_id,
              phase: s.phase === 'awaiting_clarification' ? s.phase : 'done',
            }));
            break;
          case 'error':
            setState((s) => ({ ...s, error: evt.data.error, phase: 'error' }));
            break;
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (!mountedRef.current) return;
      const body: ApiErrorBody =
        err instanceof ApiError
          ? { code: err.code, message: err.message, detail: err.detail }
          : {
              code: 'STREAM_ERROR',
              message: err instanceof Error ? err.message : 'Unknown stream error',
            };
      setState((s) => ({ ...s, error: body, phase: 'error' }));
    }
  }, []);

  const start = useCallback(
    (gen: (signal: AbortSignal) => AsyncGenerator<ChatStreamEvent>, reset: boolean) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState((s) =>
        reset ? { ...INITIAL, phase: 'streaming' } : { ...s, phase: 'streaming', error: null },
      );
      void consume(gen(controller.signal));
    },
    [consume],
  );

  /** Send a user message. `currentEngine` carries session stickiness; `mode` the
   *  ActionGate posture (plan = writes need confirmation, auto = file writes don't). */
  const send = useCallback(
    (
      message: string,
      currentEngine: EngineType | null = null,
      skillIds: string[] = [],
      mode: ComposerMode = 'plan',
    ) => {
      start(
        (signal) =>
          streamChat(
            {
              session_id: sessionId,
              message,
              current_engine: currentEngine,
              skill_ids: skillIds,
              mode,
            },
            signal,
          ),
        true,
      );
    },
    [sessionId, start],
  );

  /** Answer a clarification; resumes the stream on the chosen engine. */
  const selectClarification = useCallback(
    (optionId: string, routeTo: IntentType, mode: ComposerMode = 'plan') => {
      start(
        (signal) =>
          clarifyChat(
            { session_id: sessionId, option_id: optionId, route_to: routeTo, mode },
            signal,
          ),
        false,
      );
    },
    [sessionId, start],
  );

  const abort = useCallback(() => controllerRef.current?.abort(), []);
  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState(INITIAL);
  }, []);

  return {
    ...state,
    isStreaming: state.phase === 'streaming',
    send,
    selectClarification,
    abort,
    reset,
  };
}
