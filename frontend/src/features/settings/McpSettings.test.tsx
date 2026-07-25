import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { McpServer } from '@/types';

const listMcpServers = vi.fn();
const upsertMcpServer = vi.fn();
const deleteMcpServer = vi.fn();
const reconnectMcpServer = vi.fn();

vi.mock('@/api/mcp', () => ({
  listMcpServers: (...args: unknown[]) => listMcpServers(...args),
  upsertMcpServer: (...args: unknown[]) => upsertMcpServer(...args),
  deleteMcpServer: (...args: unknown[]) => deleteMcpServer(...args),
  reconnectMcpServer: (...args: unknown[]) => reconnectMcpServer(...args),
}));

const { McpSettings } = await import('./McpSettings');

const connected: McpServer = {
  name: 'filesystem',
  command: 'npx',
  args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
  env_keys: ['API_TOKEN'],
  enabled: true,
  status: 'connected',
  error: '',
  tools: [
    { name: 'read_text_file', capability: 'mcp__filesystem__read_text_file', description: '读文件' },
  ],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <McpSettings />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('McpSettings', () => {
  it('lists servers with their status and published capabilities', async () => {
    listMcpServers.mockResolvedValue({ servers: [connected] });

    renderPanel();

    expect(await screen.findByText('filesystem')).toBeTruthy();
    expect(screen.getByText('已连接')).toBeTruthy();
    expect(screen.getByText('read_text_file')).toBeTruthy();
    // Key names only: the backend must never echo secret values back.
    expect(screen.getByText(/env: API_TOKEN/)).toBeTruthy();
  });

  it('surfaces a failed connection instead of hiding it', async () => {
    listMcpServers.mockResolvedValue({
      servers: [{ ...connected, status: 'error', error: '无法启动 MCP 服务器', tools: [] }],
    });

    renderPanel();

    expect(await screen.findByText('连接失败')).toBeTruthy();
    expect(screen.getByText('无法启动 MCP 服务器')).toBeTruthy();
  });

  it('adds a server, splitting the pasted args on whitespace', async () => {
    listMcpServers.mockResolvedValue({ servers: [] });
    upsertMcpServer.mockResolvedValue(connected);

    renderPanel();

    fireEvent.click(await screen.findByText('添加服务器'));
    fireEvent.change(screen.getByLabelText('服务器名称'), { target: { value: 'filesystem' } });
    fireEvent.change(screen.getByLabelText('启动命令'), { target: { value: 'npx' } });
    fireEvent.change(screen.getByLabelText('启动参数'), {
      target: { value: '-y @modelcontextprotocol/server-filesystem /tmp' },
    });
    fireEvent.click(screen.getByText('保存并连接'));

    // React Query passes a second (context) argument, so assert on the input only.
    await waitFor(() => expect(upsertMcpServer).toHaveBeenCalled());
    expect(upsertMcpServer.mock.calls[0][0]).toEqual({
      name: 'filesystem',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
      env: {},
      enabled: true,
    });
  });

  it('refuses a name the backend pattern would reject', async () => {
    listMcpServers.mockResolvedValue({ servers: [] });

    renderPanel();

    fireEvent.click(await screen.findByText('添加服务器'));
    fireEvent.change(screen.getByLabelText('服务器名称'), { target: { value: 'bad name!' } });
    fireEvent.change(screen.getByLabelText('启动命令'), { target: { value: 'npx' } });

    expect((screen.getByText('保存并连接') as HTMLButtonElement).disabled).toBe(true);
  });

  it('reconnects and deletes through the real callbacks', async () => {
    listMcpServers.mockResolvedValue({ servers: [connected] });
    reconnectMcpServer.mockResolvedValue(connected);
    deleteMcpServer.mockResolvedValue(undefined);

    renderPanel();

    fireEvent.click(await screen.findByLabelText('重连 filesystem'));
    await waitFor(() => expect(reconnectMcpServer).toHaveBeenCalled());
    expect(reconnectMcpServer.mock.calls[0][0]).toBe('filesystem');

    fireEvent.click(screen.getByLabelText('删除 filesystem'));
    await waitFor(() => expect(deleteMcpServer).toHaveBeenCalled());
    expect(deleteMcpServer.mock.calls[0][0]).toBe('filesystem');
  });

  it('explains a 403 as a privileged-token mismatch', async () => {
    const { ApiError } = await import('@/api/client');
    listMcpServers.mockResolvedValue({ servers: [] });
    upsertMcpServer.mockRejectedValue(
      new ApiError(403, { code: 'HTTP_ERROR', message: '需要扩展管理凭证' }),
    );

    renderPanel();

    fireEvent.click(await screen.findByText('添加服务器'));
    fireEvent.change(screen.getByLabelText('服务器名称'), { target: { value: 'echo' } });
    fireEvent.change(screen.getByLabelText('启动命令'), { target: { value: 'node' } });
    fireEvent.click(screen.getByText('保存并连接'));

    expect((await screen.findByRole('alert')).textContent).toContain('PRIVILEGED_API_TOKEN');
  });
});
