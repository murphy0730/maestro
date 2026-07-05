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
  KNOWLEDGE_DOCS,
  KNOWLEDGE_SUPPORTED_EXTENSIONS,
  PLANNING_REPLY_TOKENS,
  QUERY_ANSWER_TOKENS,
  RAG_SOURCES,
  ROUTE_PLANNING,
  ROUTE_UNCERTAIN,
  SKILLS,
  SOLVE_RUNS,
  SOLVE_RUN_FEASIBLE,
} from './fixtures';

/** Estimate chunk count from byte size so uploads look plausible. */
const estChunks = (bytes: number) => Math.max(1, Math.round(bytes / 300));
const extOf = (name: string) => {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot).toLowerCase() : '';
};

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
    if (!sess)
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'session not found' } },
        { status: 404 },
      );
    sess.title = body.title?.trim() || '新对话';
    sess.updated_at = new Date().toISOString();
    return HttpResponse.json(sess);
  }),

  http.delete(url('/sessions/:sessionId'), ({ params }) => {
    const sid = params.sessionId as string;
    const idx = mockSessions.findIndex((s) => s.session_id === sid);
    if (idx < 0)
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'session not found' } },
        { status: 404 },
      );
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

  http.post(url('/chat/confirm'), async ({ request }) => {
    const body = (await request.json()) as { action_id: string; approved: boolean };
    await delay(200);
    return HttpResponse.json({
      reply: body.approved
        ? `已执行动作 ${body.action_id}（mock）`
        : `已取消动作 ${body.action_id}`,
      pending_actions: [
        {
          action_id: body.action_id,
          action_type: 'mock_action',
          description: '',
          params: {},
          status: body.approved ? 'executed' : 'rejected',
        },
      ],
    });
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

  /* ---- Knowledge base (RAG CRUD) ---- */
  http.get(url('/knowledge'), async () => {
    await delay(150);
    return HttpResponse.json({
      docs: [...KNOWLEDGE_DOCS].sort((a, b) => b.added_at.localeCompare(a.added_at)),
      supported_extensions: KNOWLEDGE_SUPPORTED_EXTENSIONS,
    });
  }),

  http.post(url('/knowledge'), async ({ request }) => {
    const form = await request.formData();
    const file = form.get('file') as File | null;
    if (!file) return HttpResponse.json({ detail: '缺少 file 字段' }, { status: 400 });
    const ext = extOf(file.name);
    if (!KNOWLEDGE_SUPPORTED_EXTENSIONS.includes(ext)) {
      return HttpResponse.json({ detail: `不支持的文件类型 '${ext}'` }, { status: 415 });
    }
    await delay(700); // let the progress bar animate
    const doc = {
      doc_id: `kb_${Math.random().toString(36).slice(2, 12)}`,
      name: file.name,
      type: ext.replace('.', ''),
      chunk_count: estChunks(file.size),
      bytes: file.size,
      status: 'ready' as const,
      added_at: new Date().toISOString(),
    };
    KNOWLEDGE_DOCS.push(doc);
    return HttpResponse.json(doc);
  }),

  http.put(url('/knowledge/:docId'), async ({ params, request }) => {
    const { docId } = params as { docId: string };
    const doc = KNOWLEDGE_DOCS.find((d) => d.doc_id === docId);
    if (!doc) return HttpResponse.json({ detail: `文档不存在: ${docId}` }, { status: 404 });
    const form = await request.formData();
    const file = form.get('file') as File | null;
    const name = form.get('name');
    if (file) {
      await delay(700);
      doc.name = file.name;
      doc.type = extOf(file.name).replace('.', '');
      doc.bytes = file.size;
      doc.chunk_count = estChunks(file.size);
    } else if (typeof name === 'string') {
      await delay(200);
      doc.name = name;
    } else {
      return HttpResponse.json({ detail: '需提供 file 或 name' }, { status: 400 });
    }
    return HttpResponse.json(doc);
  }),

  http.delete(url('/knowledge/:docId'), async ({ params }) => {
    const { docId } = params as { docId: string };
    const idx = KNOWLEDGE_DOCS.findIndex((d) => d.doc_id === docId);
    if (idx < 0) return HttpResponse.json({ detail: `文档不存在: ${docId}` }, { status: 404 });
    await delay(300);
    const [removed] = KNOWLEDGE_DOCS.splice(idx, 1);
    return HttpResponse.json({ doc_id: docId, removed_chunks: removed.chunk_count });
  }),

  /* ---- Skills (skill package registry CRUD) ---- */
  http.get(url('/skills'), async () => {
    await delay(150);
    return HttpResponse.json({ skills: SKILLS });
  }),

  http.post(url('/skills/import'), async ({ request }) => {
    const fd = await request.formData();
    const file = fd.get('file') as File | null;
    if (!file || !/\.(zip|md)$/i.test(file.name)) {
      return HttpResponse.json({ detail: '仅支持 .md/.zip' }, { status: 415 });
    }
    await delay(700); // let the progress bar animate
    const meta = {
      name: file.name.replace(/\.(zip|md)$/i, ''),
      display_name: file.name.replace(/\.(zip|md)$/i, ''),
      description: '已导入技能',
      when_to_use: [],
      allowed_tools: [],
      user_invocable: true,
      disable_model_invocation: false,
      tool_preconditions: {},
      file_count: 0,
      bytes: file.size,
      added_at: new Date().toISOString(),
    };
    SKILLS.push(meta);
    return HttpResponse.json(meta, { status: 201 });
  }),

  http.delete(url('/skills/:name'), async ({ params }) => {
    const { name } = params as { name: string };
    const idx = SKILLS.findIndex((s) => s.name === name);
    if (idx < 0) return HttpResponse.json({ detail: '不存在' }, { status: 404 });
    await delay(300);
    SKILLS.splice(idx, 1);
    return HttpResponse.json({ deleted: true, name });
  }),

  /* ---- Audit ---- */
  http.get(url('/audit/timeline'), async () => {
    await delay(120);
    return HttpResponse.json(AUDIT_TIMELINE);
  }),
];
