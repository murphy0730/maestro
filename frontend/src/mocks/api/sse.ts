import { HttpResponse } from 'msw';

/** One SSE frame to emit, with an optional pre-delay (ms) to simulate streaming. */
export interface SseFrame {
  event: string;
  data: unknown;
  delay?: number;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Build a streaming `text/event-stream` response that emits the given frames
 * in order, pausing `delay` ms before each. Used by the chat/query SSE mocks.
 */
export function sseResponse(frames: SseFrame[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const f of frames) {
        if (f.delay) await sleep(f.delay);
        controller.enqueue(encoder.encode(`event: ${f.event}\ndata: ${JSON.stringify(f.data)}\n\n`));
      }
      controller.close();
    },
  });
  return new HttpResponse(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
