import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiErrorBody, QueryStreamEvent, RagSource } from '@/types';
import { ApiError } from './client';
import { streamQuery } from './query';

export interface StreamingQueryState {
  phase: 'idle' | 'streaming' | 'done' | 'error';
  /** Answer text accumulated from `token` deltas. */
  text: string;
  /** RAG provenance, delivered in the final `sources` event. */
  sources: RagSource[];
  messageId: string | null;
  error: ApiErrorBody | null;
}

const INITIAL: StreamingQueryState = {
  phase: 'idle',
  text: '',
  sources: [],
  messageId: null,
  error: null,
};

/**
 * useStreamingQuery — drives the RAG `POST /query/stream`: streams answer
 * `token`s into `text`, then fills `sources` from the final event. Mirrors
 * {@link useStreamingChat}. Pure data layer.
 */
export function useStreamingQuery(sessionId: string) {
  const [state, setState] = useState<StreamingQueryState>(INITIAL);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const consume = useCallback(async (gen: AsyncGenerator<QueryStreamEvent>) => {
    try {
      for await (const evt of gen) {
        if (!mountedRef.current) return;
        switch (evt.event) {
          case 'token':
            setState((s) => ({ ...s, text: s.text + evt.data.delta }));
            break;
          case 'sources':
            setState((s) => ({ ...s, sources: evt.data.sources }));
            break;
          case 'done':
            setState((s) => ({ ...s, messageId: evt.data.message_id, phase: 'done' }));
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
          : { code: 'STREAM_ERROR', message: err instanceof Error ? err.message : 'Unknown stream error' };
      setState((s) => ({ ...s, error: body, phase: 'error' }));
    }
  }, []);

  const ask = useCallback(
    (question: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ ...INITIAL, phase: 'streaming' });
      void consume(streamQuery({ session_id: sessionId, question }, controller.signal));
    },
    [sessionId, consume],
  );

  const abort = useCallback(() => controllerRef.current?.abort(), []);
  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState(INITIAL);
  }, []);

  return { ...state, isStreaming: state.phase === 'streaming', ask, abort, reset };
}
