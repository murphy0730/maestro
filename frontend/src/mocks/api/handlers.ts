import { http, HttpResponse, delay } from 'msw';
import type {
  ChatStreamRequest,
  ClarifyRequest,
  ExecuteActionRequest,
  IntentType,
} from '@/types';
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

export const handlers = [
  /* ---- Orchestrator ---- */
  http.post(url('/chat/stream'), async ({ request }) => {
    const body = (await request.json()) as ChatStreamRequest;
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
      { event: 'route', data: { ...ROUTE_PLANNING, intent: route, source: 'clarified', confidence: 0.95 }, delay: 120 },
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
