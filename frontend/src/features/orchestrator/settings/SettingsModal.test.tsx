import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SettingsModal } from './SettingsModal';

const mockProviders = { get: vi.fn(), save: vi.fn() };

beforeEach(() => {
  mockProviders.get.mockResolvedValue({
    llm: {
      providers: [
        { id: 'p1', name: 'DeepSeek', base_url: 'u', api_key: 'k', model: 'deepseek-chat' },
      ],
      active_id: 'p1',
    },
    embedding: { providers: [], active_id: null },
  });
  mockProviders.save.mockResolvedValue({ ok: true });
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    providers: mockProviders,
    onBackendReconnecting: () => () => {},
  };
});

afterEach(() => {
  cleanup();
  delete (window as unknown as { electronAPI?: unknown }).electronAPI;
});

describe('SettingsModal', () => {
  it('lists existing providers', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    expect(await screen.findByText('DeepSeek')).toBeTruthy();
  });

  it('adds a provider via the LLM form', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    await screen.findByText('DeepSeek');
    fireEvent.change(screen.getAllByPlaceholderText('名称')[0], { target: { value: 'OpenAI' } });
    fireEvent.change(screen.getAllByPlaceholderText('base_url')[0], {
      target: { value: 'https://api.openai.com/v1' },
    });
    fireEvent.change(screen.getAllByPlaceholderText('模型 model')[0], {
      target: { value: 'gpt-4o-mini' },
    });
    fireEvent.change(screen.getAllByPlaceholderText('api_key')[0], { target: { value: 'sk-x' } });
    fireEvent.click(screen.getAllByText('添加供应商')[0]);
    await waitFor(() => expect(mockProviders.save).toHaveBeenCalled());
    const saved = mockProviders.save.mock.calls[0][0];
    expect(
      saved.llm.providers.some((p: { name: string }) => p.name === 'OpenAI'),
    ).toBe(true);
  });
});
