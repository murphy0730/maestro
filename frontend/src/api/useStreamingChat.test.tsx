import { expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ChatStreamEvent } from '@/types';

const script: ChatStreamEvent[] = [];

vi.mock('./chat', () => ({
  streamChat: async function* () {
    for (const evt of script) yield evt;
  },
  clarifyChat: async function* () {
    // unused in this test
  },
  confirmChatAction: vi.fn(),
}));

import { useStreamingChat } from './useStreamingChat';

it('consumes progress / token / actions / done frames into state', async () => {
  script.push(
    { event: 'progress', data: { text: '识别意图…' } },
    { event: 'progress', data: { text: '调用工具 check_kitting' } },
    { event: 'token', data: { delta: '已下发' } },
    {
      event: 'actions',
      data: {
        actions: [
          {
            action_id: 'a1',
            action_type: 'dispatch_work_order',
            description: '下发 WO-104',
            params: {},
            status: 'pending',
          },
        ],
      },
    },
    { event: 'done', data: { message_id: 'm1' } },
  );

  const { result } = renderHook(() => useStreamingChat('s1'));
  act(() => {
    result.current.send('下发 WO-104', 'scheduling');
  });

  await waitFor(() => expect(result.current.phase).toBe('done'));
  expect(result.current.text).toBe('已下发');
  expect(result.current.progress).toBe('调用工具 check_kitting');
  expect(result.current.actions).toHaveLength(1);
  expect(result.current.messageId).toBe('m1');
});
