import type { ChatStreamEvent, ChatStreamRequest, ClarifyRequest } from '@/types';
import { streamSse } from './streaming';

/**
 * `POST /chat/stream` — send a message and receive the orchestrator's SSE
 * stream (route → token… → clarify | context → done). Yields the typed
 * {@link ChatStreamEvent} union.
 */
export async function* streamChat(
  req: ChatStreamRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  for await (const msg of streamSse('/chat/stream', req, signal)) {
    yield msg as ChatStreamEvent;
  }
}

/**
 * `POST /chat/clarify` — answer a clarification; routes directly to the
 * chosen engine and resumes the same SSE stream.
 */
export async function* clarifyChat(
  req: ClarifyRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  for await (const msg of streamSse('/chat/clarify', req, signal)) {
    yield msg as ChatStreamEvent;
  }
}
