import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ModelsConfig } from '@/types';

const api = vi.hoisted(() => ({
  getModels: vi.fn(),
  saveModels: vi.fn(),
  testModelProvider: vi.fn(),
}));

vi.mock('@/api/models', () => ({
  getModels: api.getModels,
  saveModels: api.saveModels,
  testModelProvider: api.testModelProvider,
}));

import { ModelSettings } from './ModelSettings';

const EMPTY: ModelsConfig = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

function config(overrides: Partial<ModelsConfig['llm']>): ModelsConfig {
  return { ...EMPTY, llm: { ...EMPTY.llm, ...overrides } };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ModelSettings />
    </QueryClientProvider>,
  );
}

describe('ModelSettings', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows the degraded-mode empty state when nothing is configured', async () => {
    api.getModels.mockResolvedValue(EMPTY);
    renderPanel();
    expect(await screen.findByText('尚未添加模型 · 当前为降级模式')).toBeTruthy();
  });

  it('saves a new provider and activates it as the first entry', async () => {
    api.getModels.mockResolvedValue(EMPTY);
    api.saveModels.mockResolvedValue({ ...EMPTY, available: true });
    renderPanel();

    fireEvent.click((await screen.findAllByRole('button', { name: /添加模型/ }))[0]);
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'DeepSeek' } });
    fireEvent.change(screen.getByLabelText('model'), { target: { value: 'deepseek-chat' } });
    fireEvent.change(screen.getByLabelText('api_key'), { target: { value: 'sk-live' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(api.saveModels).toHaveBeenCalled());
    const saved = api.saveModels.mock.calls[0][0] as ModelsConfig;
    expect(saved.llm.providers[0]).toMatchObject({ name: 'DeepSeek', model: 'deepseek-chat' });
    // 第一个条目自动成为启用项。
    expect(saved.llm.active_id).toBe(saved.llm.providers[0].id);
  });

  it('switching the active entry persists the new active_id', async () => {
    api.getModels.mockResolvedValue(
      config({
        providers: [
          { id: 'a', name: '甲', base_url: 'https://a', model: 'm-a', api_key: '' },
          { id: 'b', name: '乙', base_url: 'https://b', model: 'm-b', api_key: '' },
        ],
        active_id: 'a',
      }),
    );
    api.saveModels.mockResolvedValue({ ...EMPTY, available: true });
    renderPanel();

    fireEvent.click(await screen.findByRole('radio', { name: /乙/ }));

    await waitFor(() => expect(api.saveModels).toHaveBeenCalled());
    expect((api.saveModels.mock.calls[0][0] as ModelsConfig).llm.active_id).toBe('b');
  });

  it('flags an entry whose key was never stored', async () => {
    api.getModels.mockResolvedValue(
      config({
        providers: [
          {
            id: 'a',
            name: '甲',
            base_url: 'https://a',
            model: 'm-a',
            api_key: '',
            api_key_set: false,
          },
        ],
        active_id: 'a',
      }),
    );
    renderPanel();
    expect(await screen.findByText('未配置密钥')).toBeTruthy();
  });

  it('reports the outcome of a connection test', async () => {
    api.getModels.mockResolvedValue(EMPTY);
    api.testModelProvider.mockResolvedValue({
      ok: false,
      error: '401 unauthorized',
      latency_ms: 12,
    });
    renderPanel();

    fireEvent.click((await screen.findAllByRole('button', { name: /添加模型/ }))[0]);
    fireEvent.change(screen.getByLabelText('model'), { target: { value: 'deepseek-chat' } });
    fireEvent.click(screen.getByRole('button', { name: /测试连接/ }));

    expect(await screen.findByText(/连接失败：401 unauthorized/)).toBeTruthy();
  });

  it('does not resend a blank key as a real value when editing', async () => {
    api.getModels.mockResolvedValue(
      config({
        providers: [
          {
            id: 'a',
            name: '甲',
            base_url: 'https://a',
            model: 'm-a',
            api_key: '',
            api_key_set: true,
          },
        ],
        active_id: 'a',
      }),
    );
    api.saveModels.mockResolvedValue({ ...EMPTY, available: true });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: '甲改' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(api.saveModels).toHaveBeenCalled());
    const saved = api.saveModels.mock.calls[0][0] as ModelsConfig;
    // 空密钥交给后端保留存量值，而不是覆盖成空。
    expect(saved.llm.providers[0]).toMatchObject({ id: 'a', name: '甲改', api_key: '' });
  });
});
