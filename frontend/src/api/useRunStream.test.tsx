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
      .mockImplementationOnce(async function* () { yield { event_id: '1', type: 'token.delta', data: { delta: 'A' } }; throw new Error('disconnect'); })
      .mockImplementationOnce(async function* (_run: string, lastEventId?: string) { expect(lastEventId).toBe('1'); yield { event_id: '1', type: 'token.delta', data: { delta: 'A' } }; yield { event_id: '2', type: 'run.completed', data: { final_text: 'A' } }; });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => { await result.current.start('x', [], []); });
    await waitFor(() => expect(useRunStore.getState().run?.status).toBe('completed'), { timeout: 2000 });
    expect(useRunStore.getState().tokens).toBe('A');
    expect(streamRun).toHaveBeenCalledTimes(2);
  });
  it('records an unknown parsed event as a diagnostic', async () => {
    streamRun.mockImplementationOnce(async function* () { yield { event_id: 'x', type: 'future.event', data: {}, unknown: true }; yield { event_id: 'y', type: 'run.completed', data: {} }; });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => { await result.current.start('x', [], []); });
    await waitFor(() => expect(useRunStore.getState().diagnostics[0]).toContain('future.event'));
  });

  it('clears the prior run when the active session changes', async () => {
    streamRun.mockImplementationOnce(async function* () { yield { event_id: '1', type: 'run.completed', data: { final_text: 'done' } }; });
    const { result, rerender } = renderHook(({ sessionId }) => useRunStream(sessionId), { initialProps: { sessionId: 's1' } });
    await act(async () => { await result.current.start('x', [], []); });
    await waitFor(() => expect(useRunStore.getState().run?.run_id).toBe('r1'));

    rerender({ sessionId: 's2' });

    await waitFor(() => expect(useRunStore.getState().run).toBeNull());
    expect(useRunStore.getState().tokens).toBe('');
  });
});
