import { API_BASE, ApiError } from './client';

/** A parsed Server-Sent Event: its `event:` name and JSON-decoded `data:`. */
export interface SseMessage<T = unknown> {
  event: string;
  data: T;
}

/**
 * POST a JSON body and consume a `text/event-stream` response as an async
 * iterable of parsed SSE messages. EventSource only supports GET and no body,
 * so the orchestrator/query streams are read off the fetch ReadableStream and
 * parsed by hand. `data:` lines are JSON-decoded; multi-line data is joined.
 */
export async function* streamSse<T = unknown>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<SseMessage<T>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    throw new ApiError(res.status, { code: 'STREAM_FAILED', message: `${res.status} ${res.statusText}` });
  }
  if (!res.body) {
    throw new ApiError(res.status, { code: 'STREAM_EMPTY', message: 'Response has no readable body' });
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      // SSE frames are separated by a blank line.
      let sep: number;
      while ((sep = indexOfFrameBoundary(buffer)) !== -1) {
        const rawFrame = buffer.slice(0, sep);
        buffer = buffer.slice(sep).replace(/^(\r?\n){1,2}/, '');
        const parsed = parseFrame<T>(rawFrame);
        if (parsed) yield parsed;
      }
    }
    // Flush a trailing frame with no terminating blank line.
    const tail = parseFrame<T>(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function indexOfFrameBoundary(buf: string): number {
  const lf = buf.indexOf('\n\n');
  const crlf = buf.indexOf('\r\n\r\n');
  if (lf === -1) return crlf;
  if (crlf === -1) return lf;
  return Math.min(lf, crlf);
}

function parseFrame<T>(frame: string): SseMessage<T> | null {
  const lines = frame.split(/\r?\n/);
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue; // blank or comment
    const idx = line.indexOf(':');
    const field = idx === -1 ? line : line.slice(0, idx);
    const valueRaw = idx === -1 ? '' : line.slice(idx + 1);
    const value = valueRaw.startsWith(' ') ? valueRaw.slice(1) : valueRaw;
    if (field === 'event') event = value;
    else if (field === 'data') dataLines.push(value);
  }

  if (dataLines.length === 0) return null;
  const raw = dataLines.join('\n');
  let data: T;
  try {
    data = JSON.parse(raw) as T;
  } catch {
    data = raw as unknown as T;
  }
  return { event, data };
}
