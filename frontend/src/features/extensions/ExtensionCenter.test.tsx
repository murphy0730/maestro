import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import type { McpServer, SkillMeta } from '@/types';

const api = vi.hoisted(() => ({
  listSkills: vi.fn(),
  importSkill: vi.fn(),
  validateSkill: vi.fn(),
  trustSkill: vi.fn(),
  revokeSkillTrust: vi.fn(),
  deleteSkill: vi.fn(),
  listMcpServers: vi.fn(),
  upsertMcpServer: vi.fn(),
  deleteMcpServer: vi.fn(),
  reconnectMcpServer: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
  renameSession: vi.fn(),
  deleteSession: vi.fn(),
  getSessionMessages: vi.fn(),
}));

vi.mock('@/api/skills', () => ({
  listSkills: api.listSkills,
  importSkill: api.importSkill,
  validateSkill: api.validateSkill,
  trustSkill: api.trustSkill,
  revokeSkillTrust: api.revokeSkillTrust,
  deleteSkill: api.deleteSkill,
}));
vi.mock('@/api/mcp', () => ({
  listMcpServers: api.listMcpServers,
  upsertMcpServer: api.upsertMcpServer,
  deleteMcpServer: api.deleteMcpServer,
  reconnectMcpServer: api.reconnectMcpServer,
}));
vi.mock('@/api/sessions', () => ({
  listSessions: api.listSessions,
  createSession: api.createSession,
  renameSession: api.renameSession,
  deleteSession: api.deleteSession,
  getSessionMessages: api.getSessionMessages,
}));
// `/` 只用来验证「点会话自动退出扩展中心」，不牵扯真实运行流。
vi.mock('@/pages/Workspace', () => ({ Workspace: () => <div>对话工作区</div> }));

import { routes } from '@/router';

const skills: SkillMeta[] = [
  {
    name: 'scheduling-query',
    display_name: '排产查询',
    description: '排程问答',
    scripts: ['scripts/query.py'],
    file_count: 3,
    bytes: 2048,
    added_at: '2026-07-20T00:00:00Z',
    package_sha256: 'sha-scheduling',
    compatibility_status: 'ready',
    trust: { level: 'untrusted', valid: false, package_sha256: 'sha-scheduling' },
  },
  {
    name: 'capacity-report',
    display_name: '产能日报',
    description: '产能报告',
    file_count: 1,
    bytes: 512,
    added_at: '2026-07-21T00:00:00Z',
    package_sha256: 'sha-capacity',
    compatibility_status: 'ready',
  },
];

const servers: McpServer[] = [
  {
    name: 'maestro-mes',
    command: 'python',
    args: ['/opt/mes.py'],
    env_keys: ['MES_API_KEY'],
    enabled: true,
    status: 'connected',
    error: '',
    tools: [{ name: 'query', capability: 'mcp__maestro-mes__query', description: '查询' }],
  },
  {
    name: 'env-managed',
    command: 'node',
    args: [],
    env_keys: [],
    enabled: true,
    status: 'connected',
    error: '',
    tools: [],
    managed: true,
  },
];

function open(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listSkills.mockResolvedValue({ skills });
  api.listMcpServers.mockResolvedValue({ servers });
  api.listSessions.mockResolvedValue([
    { session_id: 's1', title: '华东排产', updated_at: '2026-07-25T10:00:00Z', message_count: 1, active_run_id: null },
  ]);
  api.trustSkill.mockResolvedValue({ level: 'user_trusted', valid: true, package_sha256: 'sha' });
  api.deleteSkill.mockResolvedValue(undefined);
  api.deleteMcpServer.mockResolvedValue(undefined);
  api.reconnectMcpServer.mockResolvedValue(servers[0]);
  api.upsertMcpServer.mockResolvedValue(servers[0]);
});
afterEach(cleanup);

describe('扩展中心外框', () => {
  it('保留会话栏、换掉整个对话区，点会话即退回对话', async () => {
    open('/settings/skills');
    expect(await screen.findByRole('button', { name: '华东排产' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '扩展中心' })).toBeTruthy();
    expect(screen.queryByText('对话工作区')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '华东排产' }));
    expect(await screen.findByText('对话工作区')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '扩展中心' })).toBeNull();
  });

  it('域 Tab 换路由，搜索写进 URL query', async () => {
    const router = open('/settings/skills');
    await screen.findByRole('button', { name: '查看技能 排产查询 详情' });

    fireEvent.change(screen.getByLabelText('搜索技能'), { target: { value: '产能' } });
    await waitFor(() => expect(router.state.location.search).toBe('?q=%E4%BA%A7%E8%83%BD'));
    expect(screen.queryByRole('button', { name: '查看技能 排产查询 详情' })).toBeNull();

    // 换域重置搜索语境。
    fireEvent.click(screen.getByRole('tab', { name: '连接器' }));
    await waitFor(() => expect(router.state.location.search).toBe(''));
    await waitFor(() => expect(router.state.location.pathname).toBe('/settings/connectors'));
    expect(await screen.findByRole('button', { name: '查看连接器 maestro-mes 详情' })).toBeTruthy();
  });

  it('/settings 重定向到技能域', async () => {
    const router = open('/settings');
    await waitFor(() => expect(router.state.location.pathname).toBe('/settings/skills'));
  });
});

describe('技能管理', () => {
  it('信任脚本包，并在二次确认后才卸载', async () => {
    open('/settings/skills');
    await screen.findByRole('button', { name: '查看技能 排产查询 详情' });

    fireEvent.click(screen.getByRole('button', { name: '信任' }));
    await waitFor(() => expect(api.trustSkill.mock.calls[0]?.slice(0, 2)).toEqual(['scheduling-query', true]));

    fireEvent.click(screen.getByRole('button', { name: '卸载技能 排产查询' }));
    expect(api.deleteSkill).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '卸载技能' }));
    await waitFor(() => expect(api.deleteSkill.mock.calls[0]?.[0]).toBe('scheduling-query'));
    // 删除后必须刷新共享的 ['skills'] 列表，Composer 的选择器才不会留下幽灵项。
    await waitFor(() => expect(api.listSkills.mock.calls.length).toBeGreaterThan(1));
  });

  it('详情抽屉 Esc 关闭并把焦点还给触发按钮', async () => {
    open('/settings/skills');
    const trigger = await screen.findByRole('button', { name: '查看技能 排产查询 详情' });
    trigger.focus();
    fireEvent.click(trigger);

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('sha-scheduling')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it('预检有警告时，必须显式确认才会导入', async () => {
    api.validateSkill.mockResolvedValue({
      compatible: true,
      normalized_name: 'andon-triage',
      compatibility_status: 'ready',
      capabilities: { prompt: true, attachments: false, scripts: true },
      tool_mapping: {},
      normalized_frontmatter: {},
      warnings: ['声明兼容 Maestro >= 0.2，当前 0.2.5'],
      errors: [],
    });
    api.importSkill.mockResolvedValue({ ...skills[1], name: 'andon-triage' });

    const { container } = { container: document.body };
    open('/settings/skills?import=1');
    const drawer = await screen.findByRole('dialog');

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['# skill'], 'andon-triage.zip', { type: 'application/zip' })] },
    });

    expect(await within(drawer).findByText('预检通过')).toBeTruthy();
    expect(within(drawer).getByText(/声明兼容 Maestro/)).toBeTruthy();
    expect(api.importSkill).not.toHaveBeenCalled();

    fireEvent.click(within(drawer).getByRole('button', { name: '确认导入' }));
    await waitFor(() => expect(api.importSkill).toHaveBeenCalled());
  });
});

describe('连接器管理', () => {
  it('编辑后提交 PUT，并保留不可变的名称', async () => {
    open('/settings/connectors');
    await screen.findByRole('button', { name: '查看连接器 maestro-mes 详情' });

    fireEvent.click(screen.getByRole('button', { name: '编辑连接器 maestro-mes' }));
    const drawer = await screen.findByRole('dialog');
    expect((within(drawer).getByLabelText('服务器名称') as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(within(drawer).getByLabelText('启动命令'), {
      target: { value: 'python3' },
    });
    fireEvent.click(within(drawer).getByRole('button', { name: '保存并连接' }));

    await waitFor(() =>
      expect(api.upsertMcpServer.mock.calls[0]?.[0]).toEqual({
        name: 'maestro-mes',
        command: 'python3',
        args: ['/opt/mes.py'],
        env: { MES_API_KEY: '' },
        enabled: true,
      }),
    );
  });

  it('重连与删除：删除需二次确认', async () => {
    open('/settings/connectors');
    await screen.findByRole('button', { name: '查看连接器 maestro-mes 详情' });

    fireEvent.click(screen.getAllByRole('button', { name: '重连' })[0]);
    await waitFor(() => expect(api.reconnectMcpServer.mock.calls[0]?.[0]).toBe('maestro-mes'));

    fireEvent.click(screen.getByRole('button', { name: '删除连接器 maestro-mes' }));
    expect(api.deleteMcpServer).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '删除连接器' }));
    await waitFor(() => expect(api.deleteMcpServer.mock.calls[0]?.[0]).toBe('maestro-mes'));
  });

  it('由环境管理的连接器禁用编辑与删除', async () => {
    open('/settings/connectors');
    await screen.findByRole('button', { name: '查看连接器 env-managed 详情' });
    expect(
      (screen.getByRole('button', { name: '编辑连接器 env-managed' }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole('button', { name: '删除连接器 env-managed' }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
