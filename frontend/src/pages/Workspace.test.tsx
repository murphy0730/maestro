import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render as rtlRender, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { useRunStore } from '@/stores/runStore';
import { useSessionStore } from '@/stores/sessionStore';

const mocks = vi.hoisted(() => ({
  listSessions: vi.fn(), createSession: vi.fn(), deleteSession: vi.fn(), getSessionMessages: vi.fn(), renameSession: vi.fn(), trustSkill: vi.fn(), restore: vi.fn(), start: vi.fn(), approve: vi.fn(), cancel: vi.fn(), reconnect: vi.fn(),
}));

vi.mock('@/api', () => ({ ...mocks, useSkills: () => ({ data: { skills: [] }, isLoading: false, refetch: vi.fn(async () => ({ data: { skills: [] } })) }) }));
vi.mock('@/api/useRunStream', () => ({ useRunStream: () => ({ start: mocks.start, approve: mocks.approve, cancel: mocks.cancel, restore: mocks.restore, reconnect: mocks.reconnect, transport: 'idle', error: undefined }) }));
vi.mock('@/components/layout/Layout', () => ({ Layout: ({ sidebar, topBar, conversation }: { sidebar: React.ReactNode; topBar: React.ReactNode; conversation: React.ReactNode }) => <div>{sidebar}{topBar}{conversation}</div> }));
vi.mock('@/components/layout/SessionSidebar', () => ({ SessionSidebar: (props: { sessions: Array<{ session_id: string; title: string }>; onSelect: (id: string) => void; onCreate: () => void; onRename: (id: string, title: string) => void; onDelete: (id: string) => void; onOpenSkills: () => void }) => <nav><button onClick={props.onCreate}>测试新建</button><button onClick={props.onOpenSkills}>测试扩展中心</button>{props.sessions.map((session) => <span key={session.session_id}><button onClick={() => props.onSelect(session.session_id)}>{session.title}</button><button onClick={() => props.onRename(session.session_id, `${session.title}-改`)}>改名-{session.title}</button><button onClick={() => props.onDelete(session.session_id)}>删除-{session.title}</button></span>)}</nav> }));
vi.mock('@/components/layout/TopBar', () => ({ TopBar: ({ session }: { session: string }) => <h1>{session}</h1> }));
vi.mock('@/features/orchestrator/ConversationPanel', () => ({ ConversationPanel: ({ messages, error, onRetry }: { messages: Array<{ content: string }>; error?: string; onRetry: () => void }) => <section>{messages.map((message) => <p key={message.content}>{message.content}</p>)}{error && <><p role="alert">{error}</p><button onClick={onRetry}>重试会话</button></>}</section> }));
vi.mock('@/features/orchestrator/Composer', () => ({ Composer: () => <div>composer</div> }));
vi.mock('@/features/runtime/RunTrace', () => ({ RunTrace: () => null }));
vi.mock('@/features/orchestrator/skills/SkillImportModal', () => ({ SkillImportModal: () => null }));
vi.mock('@/features/orchestrator/skills/SkillManagerModal', () => ({ SkillManagerModal: () => null }));
vi.mock('@/features/settings/SettingsModal', () => ({ SettingsModal: () => null }));

import { Workspace } from './Workspace';

// Workspace 现在用 useNavigate 跳转扩展中心，必须在 Router 上下文里渲染。
function LocationProbe() {
  const location = useLocation();
  return <p>路由：{location.pathname}{location.search}</p>;
}
const render = () => rtlRender(<MemoryRouter><Workspace /><LocationProbe /></MemoryRouter>);

const sessions = [
  { session_id: 's1', title: '会话一', updated_at: '2026-07-25T10:00:00Z', message_count: 1, active_run_id: null },
  { session_id: 's2', title: '会话二', updated_at: '2026-07-25T09:00:00Z', message_count: 1, active_run_id: 'run-2' },
];

beforeEach(() => {
  vi.clearAllMocks();
  useRunStore.getState().reset();
  useSessionStore.getState().setActiveSessionId(null);
  mocks.listSessions.mockResolvedValue(sessions);
  mocks.createSession.mockResolvedValue({ session_id: 's3', title: '新任务', updated_at: '2026-07-25T11:00:00Z', message_count: 0 });
  mocks.deleteSession.mockResolvedValue({ deleted: true, session_id: 's1' });
  mocks.renameSession.mockImplementation(async (id: string, title: string) => ({ ...sessions.find((item) => item.session_id === id), title }));
  mocks.restore.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Workspace session orchestration', () => {
  it('restores the persisted session, its history and active run', async () => {
    useSessionStore.getState().setActiveSessionId('s2');
    mocks.getSessionMessages.mockResolvedValue([{ role: 'assistant', content: '会话二历史', ts: '2026-07-25T09:00:00Z' }]);
    render();
    expect(await screen.findByText('会话二历史')).toBeTruthy();
    expect(mocks.getSessionMessages).toHaveBeenCalledWith('s2', expect.any(AbortSignal));
    expect(mocks.restore).toHaveBeenCalledWith('run-2');
  });

  it('prevents a late history response from overwriting a newly selected session', async () => {
    let releaseOld!: (messages: unknown[]) => void;
    mocks.getSessionMessages.mockImplementation((id: string) => (
      id === 's1'
        ? new Promise((resolve) => { releaseOld = resolve; })
        : Promise.resolve([{ role: 'assistant', content: '新会话历史', ts: '2026-07-25T09:00:00Z' }])
    ));
    render();
    await screen.findByRole('button', { name: '会话二' });
    fireEvent.click(screen.getByRole('button', { name: '会话二' }));
    expect(await screen.findByText('新会话历史')).toBeTruthy();
    releaseOld([{ role: 'assistant', content: '迟到的旧历史', ts: '2026-07-25T10:00:00Z' }]);
    await Promise.resolve();
    expect(screen.queryByText('迟到的旧历史')).toBeNull();
  });

  it('actually retries a failed history request', async () => {
    mocks.getSessionMessages.mockRejectedValueOnce(new Error('history offline')).mockResolvedValueOnce([{ role: 'assistant', content: '重试成功', ts: '2026-07-25T10:00:00Z' }]);
    render();
    expect((await screen.findByRole('alert')).textContent).toContain('history offline');
    fireEvent.click(screen.getByRole('button', { name: '重试会话' }));
    expect(await screen.findByText('重试成功')).toBeTruthy();
    expect(mocks.getSessionMessages).toHaveBeenCalledTimes(2);
  });

  it('左下角入口导航到扩展中心，而不是再开一个弹窗', async () => {
    mocks.getSessionMessages.mockResolvedValue([]);
    render();
    await screen.findByRole('button', { name: '会话一' });
    fireEvent.click(screen.getByRole('button', { name: '测试扩展中心' }));
    expect(screen.getByText('路由：/settings/skills')).toBeTruthy();
  });

  it('creates, renames and deletes only after confirmation', async () => {
    mocks.getSessionMessages.mockResolvedValue([]);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render();
    await screen.findByRole('button', { name: '会话一' });
    fireEvent.click(screen.getByRole('button', { name: '改名-会话一' }));
    await vi.waitFor(() => expect(mocks.renameSession).toHaveBeenCalledWith('s1', '会话一-改'));
    fireEvent.click(await screen.findByRole('button', { name: '删除-会话一-改' }));
    await vi.waitFor(() => expect(mocks.deleteSession).toHaveBeenCalledWith('s1'));
    expect(window.confirm).toHaveBeenCalled();
    const created = { session_id: 's3', title: '新任务', updated_at: '2026-07-25T11:00:00Z', message_count: 0, active_run_id: null };
    mocks.createSession.mockResolvedValue(created);
    mocks.listSessions.mockResolvedValue([created, sessions[1]]);
    fireEvent.click(screen.getByRole('button', { name: '测试新建' }));
    expect(await screen.findByRole('button', { name: '新任务' })).toBeTruthy();
  });
});
