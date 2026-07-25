import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamRun } from './runs';

afterEach(() => vi.unstubAllGlobals());

describe('Runtime SSE parser', () => {
  it('recognizes cancelling and waiting-external lifecycle events', async () => {
    const body = [
      'id: 10\nevent: run.cancelling\ndata: {}\n\n',
      'id: 11\nevent: run.waiting_external\ndata: {}\n\n',
      'id: 12\nevent: run.controlled_started\ndata: {}\n\n',
    ].join('');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })));

    const events = [];
    for await (const event of streamRun('r1', '9')) events.push(event);

    expect(events.map((event) => event.type)).toEqual(['run.cancelling', 'run.waiting_external', 'run.controlled_started']);
    expect(events.every((event) => !('unknown' in event))).toBe(true);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/runs/r1/stream'), expect.objectContaining({ headers: expect.objectContaining({ 'Last-Event-ID': '9' }) }));
  });
});
