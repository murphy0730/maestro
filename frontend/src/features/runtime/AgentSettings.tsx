import { useEffect, useState } from 'react';
import { Settings } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { createSession, listSessions, type SessionSummary } from '@/api/sessions';
export function AgentSettings({ activeSessionId, onSessionChange }: { activeSessionId: string; onSessionChange: (sessionId: string) => void }) {
  const [open, setOpen] = useState(false); const [sessions, setSessions] = useState<SessionSummary[]>([]);
  useEffect(() => { if (open) void listSessions().then(setSessions).catch(() => setSessions([])); }, [open]);
  return <><button type="button" title="会话设置" onClick={() => setOpen(true)} className="grid h-[30px] w-[30px] place-items-center rounded-sm text-text-tertiary hover:bg-surface-2"><Settings size={16} /></button><Modal open={open} onClose={() => setOpen(false)} title="会话"><div className="space-y-3"><div className="flex items-center justify-between"><span className="text-body-sm text-text-secondary">已保存会话</span><button type="button" onClick={() => { void createSession().then((session) => { setSessions((items) => [session, ...items]); onSessionChange(session.session_id); }); }} className="text-caption text-accent">新建</button></div>{sessions.map((session) => <button key={session.session_id} type="button" onClick={() => { onSessionChange(session.session_id); setOpen(false); }} className={`block w-full rounded-sm border p-2 text-left text-body-sm ${session.session_id === activeSessionId ? 'border-accent-border bg-accent-bg text-text-primary' : 'border-border-default text-text-secondary'}`}>{session.title}</button>)}<p className="m-0 text-caption text-text-tertiary">模型、个性化与 MCP 由宿主的运行时配置管理，前端不伪造本地配置。</p></div></Modal></>;
}
