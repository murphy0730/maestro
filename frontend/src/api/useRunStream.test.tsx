import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useRunStore } from '@/stores/runStore';

const { streamRun } = vi.hoisted(() => ({ streamRun: vi.fn() }));
vi.mock('./runs', () => ({
  createRun: vi.fn(async () => ({ run_id: 'r1', session_id: 's1', objective: 'x', path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 0 })),
  getRun: vi.fn(), cancelRun: vi.fn(), resolveApproval: vi.fn(), streamRun,
}));
vi.mock('./artifacts', () => ({ uploadArtifact: vi.fn() }));
import { useRunStream } from './useRunStream';

afterEach(() => { vi.clearAllMocks(); useRunStore.getState().reset(); });
describe('useRunStream', () => {
  it('reconnects with Last-Event-ID and does not apply replayed token events twice', async () => {
    streamRun
      .mockImplementationOnce(async function* () { yield { id: '1', event: 'token.delta', data: { delta: 'A' } }; throw new Error('disconnect'); })
      .mockImplementationOnce(async function* (_run: string, lastEventId?: string) { expect(lastEventId).toBe('1'); yield { id: '1', event: 'token.delta', data: { delta: 'A' } }; yield { id: '2', event: 'run.completed', data: { final_text: 'A' } }; });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => { await result.current.start('x', [], []); });
    await waitFor(() => expect(useRunStore.getState().run?.status).toBe('completed'), { timeout: 2000 });
    expect(useRunStore.getState().tokens).toBe('A');
    expect(streamRun).toHaveBeenCalledTimes(2);
  });
});
