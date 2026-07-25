import { http, HttpResponse } from 'msw';
import { API_BASE } from '@/api/client';
import type { RunSnapshot } from '@/types/api/runs';
import type { SessionMessage, SessionSummary } from '@/api/sessions';
import type { SkillMeta } from '@/types';
import { sseResponse } from './sse';

const url = (path: string) => API_BASE.startsWith('http') ? `${API_BASE}${path}` : `*${API_BASE}${path}`;
const now = () => new Date().toISOString();
const id = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
let sessions: SessionSummary[] = [{ session_id: 'mock-default', title: '离线演示会话', updated_at: now(), message_count: 0, active_run_id: null }];
const messages = new Map<string, SessionMessage[]>([['mock-default', []]]);
const runs = new Map<string, RunSnapshot>();
let skills: SkillMeta[] = [{ name: 'offline-manufacturing', display_name: '离线制造助手', description: 'MSW 离线模式下用于验证技能选择与 run 提交。', user_invocable: true, file_count: 1, bytes: 512, added_at: now(), package_sha256: 'mock-sha256', compatibility_status: 'ready' }];
const artifacts = new Map<string, File>();

export const handlers = [
  http.get(url('/sessions'), () => HttpResponse.json(sessions)),
  http.post(url('/sessions'), async ({ request }) => { const body = await request.json() as { title?: string }; const session: SessionSummary = { session_id: id('mock-session'), title: body.title ?? '新任务', updated_at: now(), message_count: 0, active_run_id: null }; sessions = [session, ...sessions]; messages.set(session.session_id, []); return HttpResponse.json(session); }),
  http.patch(url('/sessions/:sessionId'), async ({ params, request }) => { const body = await request.json() as { title: string }; const session = sessions.find((item) => item.session_id === params.sessionId); if (!session) return HttpResponse.json({ detail: 'session not found' }, { status: 404 }); Object.assign(session, { title: body.title, updated_at: now() }); return HttpResponse.json(session); }),
  http.delete(url('/sessions/:sessionId'), ({ params }) => { const sessionId = String(params.sessionId); const exists = sessions.some((item) => item.session_id === sessionId); if (!exists) return HttpResponse.json({ detail: 'session not found' }, { status: 404 }); sessions = sessions.filter((item) => item.session_id !== sessionId); messages.delete(sessionId); return HttpResponse.json({ deleted: true, session_id: sessionId }); }),
  http.get(url('/sessions/:sessionId/messages'), ({ params }) => HttpResponse.json(messages.get(String(params.sessionId)) ?? [])),
  http.get(url('/skills'), () => HttpResponse.json({ skills })),
  http.post(url('/skills/validate'), async ({ request }) => { const file = (await request.formData()).get('file') as File; const compatible = /\.(md|zip)$/i.test(file.name); return HttpResponse.json({ compatible, normalized_name: compatible ? file.name.replace(/\.(md|zip)$/i, '') : undefined, compatibility_status: compatible ? 'ready' : 'not_ready', capabilities: { prompt: true, attachments: false, scripts: false }, tool_mapping: {}, normalized_frontmatter: {}, warnings: [], errors: compatible ? [] : ['仅支持 .md 或 .zip'] }); }),
  http.post(url('/skills/import'), async ({ request }) => { const file = (await request.formData()).get('file') as File; const skill: SkillMeta = { name: file.name.replace(/\.(md|zip)$/i, ''), description: 'MSW 导入的隔离技能', user_invocable: true, file_count: 1, bytes: file.size, added_at: now(), package_sha256: `mock-${file.size}`, compatibility_status: 'ready' }; skills = [skill, ...skills.filter((item) => item.name !== skill.name)]; return HttpResponse.json(skill); }),
  http.post(url('/skills/:name/trust'), ({ params }) => HttpResponse.json({ level: 'user_trusted', valid: true, package_sha256: `mock-${String(params.name)}` })),
  http.delete(url('/skills/:name/trust'), ({ params }) => HttpResponse.json({ level: 'untrusted', valid: true, package_sha256: `mock-${String(params.name)}` })),
  http.delete(url('/skills/:name'), ({ params }) => { skills = skills.filter((item) => item.name !== params.name); return new HttpResponse(null, { status: 204 }); }),
  http.post(url('/artifacts'), async ({ request }) => { const form = await request.formData(); const file = form.get('file') as File; const artifactId = id('mock-artifact'); artifacts.set(artifactId, file); return HttpResponse.json({ artifact_id: artifactId, sha256: artifactId, media_type: file.type || 'application/octet-stream', bytes: file.size }); }),
  http.get(url('/artifacts/:artifactId'), ({ params }) => { const file = artifacts.get(String(params.artifactId)); return file ? new HttpResponse(file, { headers: { 'Content-Type': file.type || 'application/octet-stream' } }) : HttpResponse.json({ detail: { code: 'artifact_not_found', message: 'artifact not found' } }, { status: 404 }); }),
  http.post(url('/runs'), async ({ request }) => { const body = await request.json() as { message: string; session_id: string; source?: 'chat' | 'expert' | 'event' | 'resume'; skill_names?: string[]; artifact_ids?: string[] }; const run: RunSnapshot = { run_id: id('mock-run'), session_id: body.session_id, objective: body.message, path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 1, input_artifact_ids: body.artifact_ids ?? [], intent: { requested_skills: body.skill_names ?? [], source: body.source ?? 'chat' } }; runs.set(run.run_id, run); const history = messages.get(body.session_id) ?? []; history.push({ role: 'user', content: body.message, ts: now(), skill_names: body.skill_names, artifact_ids: body.artifact_ids, run_id: run.run_id }); messages.set(body.session_id, history); const session = sessions.find((item) => item.session_id === body.session_id); if (session) Object.assign(session, { active_run_id: run.run_id, message_count: history.length, updated_at: now() }); return HttpResponse.json(run, { status: 202 }); }),
  http.get(url('/runs/:runId'), ({ params }) => { const run = runs.get(String(params.runId)); return run ? HttpResponse.json(run) : HttpResponse.json({ detail: { code: 'run_not_found', message: 'run not found' } }, { status: 404 }); }),
  http.get(url('/runs/:runId/stream'), ({ params }) => { const run = runs.get(String(params.runId)); if (run) { run.status = 'completed'; run.final_text = '正在处理制造任务。'; } return sseResponse([{ id: '1', event: 'run.path_selected', data: { path: 'fast' } }, { id: '2', event: 'token.delta', data: { delta: '正在处理制造任务。' }, delay: 80 }, { id: '3', event: 'run.completed', data: { final_text: '正在处理制造任务。' }, delay: 80 }]); }),
  http.post(url('/runs/:runId/cancel'), ({ params }) => { const run = runs.get(String(params.runId)); if (!run) return HttpResponse.json({ detail: { code: 'run_not_found', message: 'run not found' } }, { status: 404 }); run.status = 'cancelled'; return HttpResponse.json(run); }),
  http.post(url('/runs/:runId/approvals/:approvalId'), ({ params }) => { const run = runs.get(String(params.runId)); if (!run) return HttpResponse.json({ detail: { code: 'run_not_found', message: 'run not found' } }, { status: 404 }); run.status = 'running_structured'; run.pending_approvals = []; return HttpResponse.json(run); }),
];
