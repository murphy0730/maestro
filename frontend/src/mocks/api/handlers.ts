import { http, HttpResponse } from 'msw';
import { API_BASE } from '@/api/client';
import { sseResponse } from './sse';
const url = (path: string) => `${API_BASE}${path}`;
const run = { run_id: 'mock-run-1', session_id: 'default', objective: '演示运行', path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 1 };
export const handlers = [
  http.get(url('/skills'), () => HttpResponse.json({ skills: [] })),
  http.post(url('/artifacts'), async ({ request }) => { const form = await request.formData(); const file = form.get('file') as File; return HttpResponse.json({ artifact_id: `artifact-${file.name}`, sha256: `artifact-${file.name}`, media_type: file.type, bytes: file.size }); }),
  http.post(url('/runs'), async ({ request }) => { const body = await request.json() as { message: string; session_id: string }; return HttpResponse.json({ ...run, objective: body.message, session_id: body.session_id }, { status: 202 }); }),
  http.get(url('/runs/:runId/stream'), () => sseResponse([{ event: 'run.path_selected', data: { path: 'fast' } }, { event: 'token.delta', data: { delta: '正在处理制造任务。' } }, { event: 'run.completed', data: { final_text: '正在处理制造任务。' } }])),
  http.post(url('/runs/:runId/cancel'), () => HttpResponse.json({ ...run, status: 'cancelled' })),
  http.post(url('/runs/:runId/approvals/:approvalId'), () => HttpResponse.json({ ...run, status: 'running_structured', pending_approvals: [] })),
];
