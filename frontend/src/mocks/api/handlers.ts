import { http, HttpResponse, delay } from 'msw';
import type { ChatStreamRequest, ClarifyRequest, ExecuteActionRequest, IntentType } from '@/types';
import { API_BASE } from '@/api/client';
import { sseResponse, type SseFrame } from './sse';
import {
  AUDIT_TIMELINE,
  CLARIFY_4830,
  DISPATCH_ORDERS,
  EXCEPTION_IMPACT,
  KITTING,
  PLANNING_REPLY_TOKENS,
  QUERY_ANSWER_TOKENS,
  RAG_SOURCES,
  ROUTE_PLANNING,
  ROUTE_UNCERTAIN,
  SOLVE_RUNS,
  SOLVE_RUN_FEASIBLE,
} from './fixtures';

const url = (path: string) => `${API_BASE}${path}`;

// In-memory session store for mock mode (resets on page refresh)
interface MockSession {
  session_id: string;
  title: string;
  engine: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}
const mockSessions: MockSession[] = [];
const mockMessages: Record<string, Array<{ role: string; content: string; ts: string }>> = {};

/** Tokens → SSE `token` frames with a per-token delay to mimic streaming. */
const tokenFrames = (tokens: string[], step = 220): SseFrame[] =>
  tokens.map((t) => ({ event: 'token', data: { delta: t }, delay: step }));

/** Build the planning reply stream (route → tokens → context → done). */
function planningStream(): SseFrame[] {
  return [
    { event: 'route', data: ROUTE_PLANNING, delay: 150 },
    ...tokenFrames(PLANNING_REPLY_TOKENS),
    { event: 'context', data: { engine: 'planning', payload: SOLVE_RUN_FEASIBLE }, delay: 200 },
    { event: 'done', data: { message_id: `msg-${Date.now()}` }, delay: 80 },
  ];
}

/**
 * 无 LLM 的 mock 端：把首条消息取第一个语义子句作为会话标题，
 * 比整句截断更接近真实后端的「有意义摘要」（真实后端走 LLM 生成）。
 */
function deriveMockTitle(message: string): string {
  const firstClause = message.split(/[，。！？、;；\n,.!?]/).find((s) => s.trim()) ?? message;
  const title = firstClause.trim();
  return title.length > 12 ? title.slice(0, 12) + '…' : title;
}

export const handlers = [
  /* ---- Sessions ---- */
  http.get(url('/sessions'), () => HttpResponse.json(mockSessions)),

  http.post(url('/sessions'), async ({ request }) => {
    const body = (await request.json()) as { title?: string };
    const session: MockSession = {
      session_id: crypto.randomUUID().replace(/-/g, ''),
      title: body.title ?? '新对话',
      engine: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      message_count: 0,
    };
    mockSessions.unshift(session);
    mockMessages[session.session_id] = [];
    return HttpResponse.json(session, { status: 201 });
  }),

  http.get(url('/sessions/:sessionId/messages'), ({ params }) => {
    const msgs = mockMessages[params.sessionId as string] ?? [];
    return HttpResponse.json(msgs);
  }),

  http.patch(url('/sessions/:sessionId'), async ({ params, request }) => {
    const body = (await request.json()) as { title?: string };
    const sess = mockSessions.find((s) => s.session_id === params.sessionId);
    if (!sess) return HttpResponse.json({ error: { code: 'NOT_FOUND', message: 'session not found' } }, { status: 404 });
    sess.title = body.title?.trim() || '新对话';
    sess.updated_at = new Date().toISOString();
    return HttpResponse.json(sess);
  }),

  http.delete(url('/sessions/:sessionId'), ({ params }) => {
    const sid = params.sessionId as string;
    const idx = mockSessions.findIndex((s) => s.session_id === sid);
    if (idx < 0) return HttpResponse.json({ error: { code: 'NOT_FOUND', message: 'session not found' } }, { status: 404 });
    mockSessions.splice(idx, 1);
    delete mockMessages[sid];
    return HttpResponse.json({ deleted: true, session_id: sid });
  }),

  /* ---- Orchestrator ---- */
  http.post(url('/chat/stream'), async ({ request }) => {
    const body = (await request.json()) as ChatStreamRequest;
    // Record user message in mock session store
    const sid = body.session_id;
    if (sid && mockMessages[sid]) {
      mockMessages[sid].push({
        role: 'user',
        content: body.message ?? '',
        ts: new Date().toISOString(),
      });
      const sess = mockSessions.find((s) => s.session_id === sid);
      if (sess) {
        sess.message_count = mockMessages[sid].length;
        sess.updated_at = new Date().toISOString();
        if (sess.title === '新对话' && body.message) {
          sess.title = deriveMockTitle(body.message);
        }
      }
    }
    const text = body.message ?? '';
    // Ambiguous intent → clarify (mirrors the WO-4830 急单 demo).
    if (/4830|急单|插队/.test(text)) {
      return sseResponse([
        { event: 'route', data: ROUTE_UNCERTAIN, delay: 150 },
        { event: 'clarify', data: CLARIFY_4830, delay: 200 },
        { event: 'done', data: { message_id: `msg-${Date.now()}` }, delay: 60 },
      ]);
    }
    return sseResponse(planningStream());
  }),

  http.post(url('/chat/clarify'), async ({ request }) => {
    const body = (await request.json()) as ClarifyRequest;
    const route: IntentType = body.route_to;
    const isScheduling = route === 'scheduling';
    return sseResponse([
      {
        event: 'route',
        data: { ...ROUTE_PLANNING, intent: route, source: 'clarified', confidence: 0.95 },
        delay: 120,
      },
      {
        event: 'token',
        data: {
          delta: isScheduling
            ? '已按插队调度处理：插入 WO-4830，触发 A→B 换型 45 分钟。'
            : '已将 WO-4830 纳入明日整体重排：与现有工单一并求解。',
        },
        delay: 220,
      },
      {
        event: 'context',
        data: { engine: route, payload: isScheduling ? DISPATCH_ORDERS : SOLVE_RUN_FEASIBLE },
        delay: 200,
      },
      { event: 'done', data: { message_id: `msg-${Date.now()}` }, delay: 60 },
    ]);
  }),

  /* ---- Planning ---- */
  http.post(url('/planning/solve'), async () => {
    await delay(600);
    return HttpResponse.json(SOLVE_RUN_FEASIBLE);
  }),

  http.get(url('/planning/solve-runs'), async () => {
    await delay(120);
    return HttpResponse.json(SOLVE_RUNS);
  }),

  /* ---- Scheduling ---- */
  http.get(url('/scheduling/kitting'), async () => {
    await delay(120);
    return HttpResponse.json(KITTING);
  }),

  http.get(url('/scheduling/dispatch-orders'), async () => {
    await delay(120);
    return HttpResponse.json(DISPATCH_ORDERS);
  }),

  http.post(url('/scheduling/execute'), async ({ request }) => {
    const body = (await request.json()) as ExecuteActionRequest;
    await delay(400);
    const order = DISPATCH_ORDERS.orders.find((o) => o.id === body.action_id);
    // requires_confirmation actions need confirmed=true.
    if (order?.authorization === 'requires_confirmation' && !body.confirmed) {
      return HttpResponse.json({
        status: 'rejected',
        audit_id: `audit-${Date.now()}`,
        message: '该动作需二次确认（confirmed=true）后才能执行',
      });
    }
    return HttpResponse.json({
      status: 'executed',
      audit_id: `audit-${Date.now()}`,
      message: `已下发 ${body.action_id} 至产线`,
    });
  }),

  http.get(url('/scheduling/exception-impact'), async () => {
    await delay(150);
    return HttpResponse.json(EXCEPTION_IMPACT);
  }),

  /* ---- Query (RAG) ---- */
  http.post(url('/query/stream'), async () => {
    return sseResponse([
      ...tokenFrames(QUERY_ANSWER_TOKENS, 240),
      { event: 'sources', data: { sources: RAG_SOURCES }, delay: 200 },
      { event: 'done', data: { message_id: `msg-${Date.now()}` }, delay: 60 },
    ]);
  }),

  /* ---- Audit ---- */
  http.get(url('/audit/timeline'), async () => {
    await delay(120);
    return HttpResponse.json(AUDIT_TIMELINE);
  }),
];
