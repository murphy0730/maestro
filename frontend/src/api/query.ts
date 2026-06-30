import type { AuditTimelineResponse, QueryStreamEvent, QueryStreamRequest } from '@/types';
import { apiGet, withQuery } from './client';
import { streamSse } from './streaming';

/**
 * `POST /query/stream` — RAG query. Streams answer `token`s then a final
 * `sources` event. Yields the typed {@link QueryStreamEvent} union.
 */
export async function* streamQuery(
  req: QueryStreamRequest,
  signal?: AbortSignal,
): AsyncGenerator<QueryStreamEvent> {
  for await (const msg of streamSse('/query/stream', req, signal)) {
    yield msg as QueryStreamEvent;
  }
}

/** `GET /audit/timeline` — decision-log timeline for the observability drawer. */
export function getAuditTimeline(sessionId: string, signal?: AbortSignal): Promise<AuditTimelineResponse> {
  return apiGet<AuditTimelineResponse>(withQuery('/audit/timeline', { session_id: sessionId }), { signal });
}
