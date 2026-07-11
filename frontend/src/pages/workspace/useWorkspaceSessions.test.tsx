import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  let resolveMessages: (messages: unknown[]) => void = () => undefined;
  return {
    getSessionMessages: vi.fn(
      () =>
        new Promise<unknown[]>((resolve) => {
          resolveMessages = resolve;
        }),
    ),
    resolveMessages: (messages: unknown[]) => resolveMessages(messages),
  };
});

vi.mock('@/api', () => ({
  useSessions: () => ({
    data: [
      {
        session_id: 's1',
        title: '已有会话',
        engine: null,
        created_at: '2026-07-11T00:00:00Z',
        updated_at: '2026-07-11T00:00:00Z',
        message_count: 1,
      },
    ],
    isSuccess: true,
    refetch: vi.fn(),
  }),
  useCreateSession: () => ({ mutateAsync: vi.fn() }),
  useDeleteSession: () => ({ mutateAsync: vi.fn() }),
  useRenameSession: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock('@/api/sessions', () => ({
  getSessionMessages: mocks.getSessionMessages,
}));

import { useConversationStore } from '@/stores';
import { useSessionStore } from '@/stores/sessionStore';
import { useWorkspaceSessions } from './useWorkspaceSessions';

beforeEach(() => {
  mocks.getSessionMessages.mockClear();
  useSessionStore.getState().setActiveSessionId(null);
  useConversationStore.getState().resetThread();
});

it('does not overwrite messages added while session history is loading', async () => {
  renderHook(() => useWorkspaceSessions({ onFreshConversation: vi.fn() }));
  await waitFor(() => expect(mocks.getSessionMessages).toHaveBeenCalledWith('s1'));

  act(() => {
    useConversationStore.getState().addMessage({ id: 'new', kind: 'user', text: '你是谁' });
    mocks.resolveMessages([
      { role: 'assistant', content: '旧消息', ts: '2026-07-11T00:00:00Z' },
    ]);
  });

  await waitFor(() =>
    expect(useConversationStore.getState().messages.some((message) => message.id === 'new')).toBe(
      true,
    ),
  );
  expect(
    useConversationStore
      .getState()
      .messages.some((message) => 'text' in message && message.text === '旧消息'),
  ).toBe(false);
});
