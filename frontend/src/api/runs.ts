import { AGENT_API_PREFIX, API_BASE, apiGet, apiPost, authHeaders } from './client';
import type { AgentEvent, CreateRunRequest, RunSnapshot } from '@/types/api/runs';

export const createRun = ({ session_id: sessionId, ...request }: CreateRunRequest) =>
  apiPost<RunSnapshot>(`${AGENT_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/runs`, request);
export const getRun = (runId: string) => apiGet<RunSnapshot>(`${AGENT_API_PREFIX}/runs/${encodeURIComponent(runId)}`);
export const cancelRun = (runId: string) => apiPost<RunSnapshot>(`${AGENT_API_PREFIX}/runs/${encodeURIComponent(runId)}/cancel`, {});
export const resolveApproval = (runId: string, approvalId: string, approved: boolean, expectedRevision: number) =>
  apiPost<{ accepted: true; run_id: string; approval_id: string }>(`${AGENT_API_PREFIX}/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`, { approved, expected_revision: expectedRevision, principal_id: 'local-user' });

export async function* streamRun(runId: string, lastEventId?: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const response = await fetch(`${API_BASE}${AGENT_API_PREFIX}/runs/${encodeURIComponent(runId)}/stream`, {
    headers: { Accept: 'text/event-stream', ...authHeaders(), ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}) }, signal,
  });
  if (!response.ok || !response.body) throw new Error(`Run stream failed: ${response.status}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let boundary: number;
      while ((boundary = buffer.search(/\r?\n\r?\n/)) >= 0) {
        const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary).replace(/^\r?\n\r?\n/, '');
        const fields = Object.fromEntries(frame.split(/\r?\n/).map((line) => { const index = line.indexOf(':'); return [index < 0 ? line : line.slice(0, index), index < 0 ? '' : line.slice(index + 1).trimStart()]; }));
        if (fields.data) {
          const data = JSON.parse(fields.data) as AgentEvent;
          if (data.event_type) yield { ...data, event_id: data.event_id || fields.id || undefined };
          else yield { event_id: fields.id || undefined, type: fields.event || 'message', data: data as Record<string, unknown> };
        }
      }
    }
  } finally { reader.releaseLock(); }
}
