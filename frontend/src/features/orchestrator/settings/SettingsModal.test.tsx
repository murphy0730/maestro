import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SettingsModal } from './SettingsModal';

const mockConfig = {
  llm: {
    providers: [
      { id: 'p1', name: 'DeepSeek', base_url: 'u', api_key: 'k', model: 'deepseek-chat' },
    ],
    active_id: 'p1',
  },
  embedding: { providers: [], active_id: null },
};

const fetchMock = vi.fn();
let originalFetch: typeof fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  fetchMock.mockImplementation(async (url: string | URL, opts?: { method?: string }) => {
    const u = url.toString();
    if (u.includes('/models') && (!opts?.method || opts.method === 'GET')) {
      return { ok: true, json: async () => mockConfig };
    }
    if (opts?.method === 'PUT' && u.includes('/models')) {
      return { ok: true, json: async () => ({ ok: true, available: true }) };
    }
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.stubGlobal('fetch', originalFetch);
  cleanup();
});

describe('SettingsModal', () => {
  it('lists existing providers from settings.json (GET /models)', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    expect(await screen.findByText('DeepSeek')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/models'));
  });

  it('adds a provider via the LLM form (PUT /models)', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    await screen.findByText('DeepSeek');
    fireEvent.click(screen.getAllByText('添加模型')[0]);
    fireEvent.change(screen.getAllByPlaceholderText('如 DeepSeek')[0], {
      target: { value: 'OpenAI' },
    });
    fireEvent.change(screen.getAllByPlaceholderText('如 deepseek-chat')[0], {
      target: { value: 'gpt-4o-mini' },
    });
    fireEvent.change(screen.getAllByPlaceholderText('https://api.deepseek.com/v1')[0], {
      target: { value: 'https://api.openai.com/v1' },
    });
    fireEvent.change(screen.getAllByPlaceholderText('sk-...')[0], { target: { value: 'sk-x' } });
    fireEvent.click(screen.getAllByText('保存')[0]);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/models'),
        expect.objectContaining({ method: 'PUT' }),
      ),
    );
    const putCall = fetchMock.mock.calls.find(
      (c) => (c[1] as { method?: string })?.method === 'PUT',
    );
    const saved = JSON.parse((putCall![1] as { body: string }).body);
    expect(saved.llm.providers.some((p: { name: string }) => p.name === 'OpenAI')).toBe(true);
  });
});
