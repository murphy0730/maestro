import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render as rtlRender, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { useRunStore } from '@/stores/runStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useUiPreferencesStore } from '@/stores/uiPreferencesStore';

const mocks = vi.hoisted(() => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  deleteSessionMessage: vi.fn(),
  getSessionMessages: vi.fn(),
  renameSession: vi.fn(),
  trustSkill: vi.fn(),
  restore: vi.fn(),
  start: vi.fn(),
  approve: vi.fn(),
  cancel: vi.fn(),
  reconnect: vi.fn(),
}));

vi.mock('@/api', () => ({
  ...mocks,
  useSkills: () => ({
    data: { skills: [] },
    isLoading: false,
    refetch: vi.fn(async () => ({ data: { skills: [] } })),
  }),
}));
vi.mock('@/api/useRunStream', () => ({
  useRunStream: () => ({
    start: mocks.start,
    approve: mocks.approve,
    cancel: mocks.cancel,
    restore: mocks.restore,
    reconnect: mocks.reconnect,
    transport: 'idle',
    error: undefined,
  }),
}));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({
    sidebar,
    topBar,
    conversation,
  }: {
    sidebar: React.ReactNode;
    topBar: React.ReactNode;
    conversation: React.ReactNode;
  }) => (
    <div>
      {sidebar}
      {topBar}
      {conversation}
    </div>
  ),
}));
vi.mock('@/components/layout/SessionSidebar', () => ({
  SessionSidebar: (props: {
    sessions: Array<{ session_id: string; title: string }>;
    onSelect: (id: string) => void;
    onCreate: () => void;
    onRename: (id: string, title: string) => void;
    onDelete: (id: string) => void;
    onOpenSkills: () => void;
  }) => (
    <nav>
      <button onClick={props.onCreate}>测试新建</button>
      <button onClick={props.onOpenSkills}>测试扩展中心</button>
      {props.sessions.map((session) => (
        <span key={session.session_id}>
          <button onClick={() => props.onSelect(session.session_id)}>{session.title}</button>
          <button onClick={() => props.onRename(session.session_id, `${session.title}-改`)}>
            改名-{session.title}
          </button>
          <button onClick={() => props.onDelete(session.session_id)}>删除-{session.title}</button>
        </span>
      ))}
    </nav>
  ),
}));
vi.mock('@/components/layout/TopBar', () => ({
  TopBar: ({ session }: { session: string }) => <h1>{session}</h1>,
}));
vi.mock('@/features/orchestrator/ConversationPanel', () => ({
  ConversationPanel: ({
    messages,
    error,
    onRetry,
    onDeleteMessage,
  }: {
    messages: Array<{ id?: string; role: string; content: string }>;
    error?: string;
    onRetry: () => void;
    onDeleteMessage: (messageId: string, cascade: boolean) => void;
  }) => (
    <section>
      {messages.map((message, index) => (
        <div key={message.content}>
          <p>{message.content}</p>
          <button
            onClick={() =>
              onDeleteMessage(
                message.id!,
                message.role === 'user' && messages[index + 1]?.role === 'assistant',
              )
            }
          >
            删除-{message.content}
          </button>
        </div>
      ))}
      {error && (
        <>
          <p role="alert">{error}</p>
          <button onClick={onRetry}>重试会话</button>
        </>
      )}
    </section>
  ),
}));
vi.mock('@/features/orchestrator/Composer', () => ({
  Composer: ({ onSend }: { onSend: (message: string, files: File[]) => Promise<void> }) => (
    <>
      <button onClick={() => void onSend('立即显示的消息', [])}>测试发送</button>
      <button
        onClick={() =>
          void onSend('将所有班次改成周日不上班，然后跑一次 ATC 并对比基线', [])
        }
      >
        测试 What-if
      </button>
    </>
  ),
}));
vi.mock('@/features/runtime/RunTrace', () => ({
  RunTrace: ({ view }: { view: string }) => <p>运行详情视图：{view}</p>,
}));
vi.mock('@/features/orchestrator/skills/SkillImportModal', () => ({
  SkillImportModal: () => null,
}));
vi.mock('@/features/orchestrator/skills/SkillManagerModal', () => ({
  SkillManagerModal: () => null,
}));
vi.mock('@/features/settings/SettingsModal', () => ({ SettingsModal: () => null }));

import { Workspace } from './Workspace';

// Workspace 现在用 useNavigate 跳转扩展中心，必须在 Router 上下文里渲染。
function LocationProbe() {
  const location = useLocation();
  return (
    <p>
      路由：{location.pathname}
      {location.search}
    </p>
  );
}
const render = () =>
  rtlRender(
    <MemoryRouter>
      <Workspace />
      <LocationProbe />
    </MemoryRouter>,
  );

const sessions = [
  {
    session_id: 's1',
    title: '会话一',
    updated_at: '2026-07-25T10:00:00Z',
    message_count: 1,
    active_run_id: null,
  },
  {
    session_id: 's2',
    title: '会话二',
    updated_at: '2026-07-25T09:00:00Z',
    message_count: 1,
    active_run_id: 'run-2',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  useRunStore.getState().reset();
  useSessionStore.getState().setActiveSessionId(null);
  useUiPreferencesStore.setState({ traceDefault: 'docked' });
  mocks.listSessions.mockResolvedValue(sessions);
  mocks.createSession.mockResolvedValue({
    session_id: 's3',
    title: '新任务',
    updated_at: '2026-07-25T11:00:00Z',
    message_count: 0,
  });
  mocks.deleteSession.mockResolvedValue({ deleted: true, session_id: 's1' });
  mocks.deleteSessionMessage.mockResolvedValue({
    deleted: true,
    session_id: 's1',
    message_index: 0,
  });
  mocks.renameSession.mockImplementation(async (id: string, title: string) => ({
    ...sessions.find((item) => item.session_id === id),
    title,
  }));
  mocks.restore.mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Workspace session orchestration', () => {
  it('restores the persisted session, its history and active run', async () => {
    useSessionStore.getState().setActiveSessionId('s2');
    mocks.getSessionMessages.mockResolvedValue([
      { role: 'assistant', content: '会话二历史', ts: '2026-07-25T09:00:00Z' },
    ]);
    render();
    expect(await screen.findByText('会话二历史')).toBeTruthy();
    expect(mocks.getSessionMessages).toHaveBeenCalledWith('s2', expect.any(AbortSignal));
    expect(mocks.restore).toHaveBeenCalledWith('run-2');
  });

  it('prevents a late history response from overwriting a newly selected session', async () => {
    let releaseOld!: (messages: unknown[]) => void;
    mocks.getSessionMessages.mockImplementation((id: string) =>
      id === 's1'
        ? new Promise((resolve) => {
            releaseOld = resolve;
          })
        : Promise.resolve([
            { role: 'assistant', content: '新会话历史', ts: '2026-07-25T09:00:00Z' },
          ]),
    );
    render();
    await screen.findByRole('button', { name: '会话二' });
    fireEvent.click(screen.getByRole('button', { name: '会话二' }));
    expect(await screen.findByText('新会话历史')).toBeTruthy();
    releaseOld([{ role: 'assistant', content: '迟到的旧历史', ts: '2026-07-25T10:00:00Z' }]);
    await Promise.resolve();
    expect(screen.queryByText('迟到的旧历史')).toBeNull();
  });

  it('actually retries a failed history request', async () => {
    mocks.getSessionMessages
      .mockRejectedValueOnce(new Error('history offline'))
      .mockResolvedValueOnce([
        { role: 'assistant', content: '重试成功', ts: '2026-07-25T10:00:00Z' },
      ]);
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
    const created = {
      session_id: 's3',
      title: '新任务',
      updated_at: '2026-07-25T11:00:00Z',
      message_count: 0,
      active_run_id: null,
    };
    mocks.createSession.mockResolvedValue(created);
    mocks.listSessions.mockResolvedValue([created, sessions[1]]);
    fireEvent.click(screen.getByRole('button', { name: '测试新建' }));
    expect(await screen.findByRole('button', { name: '新任务' })).toBeTruthy();
  });

  it('shows the user message before run creation finishes', async () => {
    let finishStart!: (run: Record<string, unknown>) => void;
    mocks.getSessionMessages.mockResolvedValue([]);
    mocks.start.mockReturnValue(
      new Promise((resolve) => {
        finishStart = resolve;
      }),
    );
    render();
    await screen.findByRole('button', { name: '会话一' });

    fireEvent.click(screen.getByRole('button', { name: '测试发送' }));

    expect(await screen.findByText('立即显示的消息')).toBeTruthy();
    finishStart({ run_id: 'run-new', input_artifact_ids: [] });
    await vi.waitFor(() => expect(mocks.start).toHaveBeenCalledOnce());
  });

  it('automatically loads the What-if skill for a hypothetical scheduling request', async () => {
    mocks.getSessionMessages.mockResolvedValue([]);
    mocks.start.mockResolvedValue({ run_id: 'whatif-run', input_artifact_ids: [] });
    render();
    await screen.findByRole('button', { name: '会话一' });

    fireEvent.click(screen.getByRole('button', { name: '测试 What-if' }));

    await vi.waitFor(() =>
      expect(mocks.start).toHaveBeenCalledWith(
        '将所有班次改成周日不上班，然后跑一次 ATC 并对比基线',
        [],
        ['whatif-planning'],
      ),
    );
  });

  it('reveals a hidden run trace when a new approval is waiting', async () => {
    mocks.getSessionMessages.mockResolvedValue([]);
    useUiPreferencesStore.setState({ traceDefault: 'hidden' });
    render();
    await screen.findByRole('button', { name: '会话一' });
    expect(screen.getByText('运行详情视图：hidden')).toBeTruthy();

    act(() => {
      useRunStore.getState().setRun({
        run_id: 'run-approval',
        session_id: 's1',
        objective: '修改班次',
        path: 'structured',
        status: 'waiting_approval',
        steps: {},
        revision: 4,
        pending_approvals: [
          {
            approval_id: 'approval-1',
            step_id: 'apply-patch',
            impact_summary: '修改周日班次',
            policy_reason: 'high-risk write requires confirmation',
            run_revision: 4,
            status: 'pending',
          },
        ],
      });
    });

    expect(await screen.findByText('运行详情视图：docked')).toBeTruthy();
  });

  it('removes every message the server reports deleted and refreshes session metadata', async () => {
    mocks.getSessionMessages.mockResolvedValue([
      { id: 'm1', role: 'user', content: '要删除的消息', ts: '2026-07-25T10:00:00Z' },
      { id: 'm2', role: 'assistant', content: '这轮的回复', ts: '2026-07-25T10:00:01Z' },
    ]);
    mocks.deleteSessionMessage.mockResolvedValue({
      deleted: true,
      session_id: 's1',
      deleted_ids: ['m1', 'm2'],
    });
    render();
    const deleteButton = await screen.findByRole('button', { name: '删除-要删除的消息' });
    const listCallsBeforeDelete = mocks.listSessions.mock.calls.length;
    fireEvent.click(deleteButton);

    await vi.waitFor(() =>
      expect(mocks.deleteSessionMessage).toHaveBeenCalledWith('s1', 'm1', true),
    );
    await vi.waitFor(() => expect(screen.queryByText('要删除的消息')).toBeNull());
    expect(screen.queryByText('这轮的回复')).toBeNull();
    await vi.waitFor(() =>
      expect(mocks.listSessions).toHaveBeenCalledTimes(listCallsBeforeDelete + 1),
    );
  });
});
