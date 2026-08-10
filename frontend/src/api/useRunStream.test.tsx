import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRunStore } from '@/stores/runStore';

const mocks = vi.hoisted(() => ({
  streamRun: vi.fn(),
  createRun: vi.fn(),
  getRun: vi.fn(),
  cancelRun: vi.fn(),
  resolveApproval: vi.fn(),
  uploadArtifact: vi.fn(),
}));
vi.mock('./runs', () => ({
  createRun: mocks.createRun,
  getRun: mocks.getRun,
  cancelRun: mocks.cancelRun,
  resolveApproval: mocks.resolveApproval,
  streamRun: mocks.streamRun,
}));
vi.mock('./artifacts', () => ({ uploadArtifact: mocks.uploadArtifact }));
import { useRunStream } from './useRunStream';

beforeEach(() => {
  mocks.streamRun.mockReset();
  mocks.createRun
    .mockReset()
    .mockResolvedValue({
      run_id: 'r1',
      session_id: 's1',
      objective: 'x',
      path: 'fast',
      status: 'running_fast',
      steps: {},
      pending_approvals: [],
      revision: 0,
    });
  mocks.getRun
    .mockReset()
    .mockImplementation(async (id: string) => ({
      run_id: id,
      session_id: 's1',
      objective: 'restored',
      path: 'structured',
      status: 'waiting_approval',
      steps: {},
      pending_approvals: [{ approval_id: 'a1' }],
      revision: 2,
    }));
  mocks.cancelRun.mockReset();
  mocks.resolveApproval.mockReset();
  mocks.uploadArtifact.mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
  useRunStore.getState().reset();
});
describe('useRunStream', () => {
  it('reconnects with Last-Event-ID and does not apply replayed token events twice', async () => {
    mocks.streamRun
      .mockImplementationOnce(async function* () {
        yield { event_id: '1', type: 'token.delta', data: { delta: 'A' } };
        throw new Error('disconnect');
      })
      .mockImplementationOnce(async function* (_run: string, lastEventId?: string) {
        expect(lastEventId).toBe('1');
        yield { event_id: '1', type: 'token.delta', data: { delta: 'A' } };
        yield { event_id: '2', type: 'run.completed', data: { final_text: 'A' } };
      });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.start('x', [], []);
    });
    await waitFor(() => expect(useRunStore.getState().run?.status).toBe('completed'), {
      timeout: 2000,
    });
    expect(useRunStore.getState().tokens).toBe('A');
    expect(mocks.streamRun).toHaveBeenCalledTimes(2);
  });

  it('reconciles the durable snapshot when the stream closes without a terminal event', async () => {
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: '1', type: 'step.succeeded', data: { step_id: 'read' } };
    });
    mocks.getRun.mockResolvedValue({
      run_id: 'r1',
      session_id: 's1',
      objective: 'x',
      path: 'fast',
      status: 'completed',
      steps: {},
      pending_approvals: [],
      revision: 3,
      final_text: 'done',
    });
    const { result } = renderHook(() => useRunStream('s1'));

    await act(async () => {
      await result.current.start('x', [], []);
    });

    await waitFor(() => expect(useRunStore.getState().run?.status).toBe('completed'));
    expect(result.current.transport).toBe('idle');
  });

  it('polls the durable snapshot when an open stream misses the terminal event', async () => {
    vi.useFakeTimers();
    try {
      mocks.streamRun.mockImplementationOnce(async function* (
        _runId: string,
        _lastEventId?: string,
        signal?: AbortSignal,
      ) {
        yield { event_id: 'open', type: 'token.delta', data: { delta: '' } };
        await new Promise<void>((resolve) =>
          signal?.addEventListener('abort', () => resolve(), { once: true }),
        );
      });
      mocks.getRun.mockResolvedValue({
        run_id: 'r1',
        session_id: 's1',
        objective: 'x',
        path: 'structured',
        status: 'completed',
        steps: {},
        pending_approvals: [],
        revision: 8,
        final_text: 'done',
      });
      const { result } = renderHook(() => useRunStream('s1'));
      await act(async () => {
        await result.current.start('x', [], []);
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });

      expect(useRunStore.getState().run?.status).toBe('completed');
      expect(result.current.transport).toBe('idle');
    } finally {
      vi.useRealTimers();
    }
  });
  it('records an unknown parsed event as a diagnostic', async () => {
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: 'x', type: 'future.event', data: {}, unknown: true };
      yield { event_id: 'y', type: 'run.completed', data: {} };
    });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.start('x', [], []);
    });
    await waitFor(() => expect(useRunStore.getState().diagnostics[0]).toContain('future.event'));
  });

  it('clears the prior run when the active session changes', async () => {
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: '1', type: 'run.completed', data: { final_text: 'done' } };
    });
    const { result, rerender } = renderHook(({ sessionId }) => useRunStream(sessionId), {
      initialProps: { sessionId: 's1' },
    });
    await act(async () => {
      await result.current.start('x', [], []);
    });
    await waitFor(() => expect(useRunStore.getState().run?.run_id).toBe('r1'));

    rerender({ sessionId: 's2' });

    await waitFor(() => expect(useRunStore.getState().run).toBeNull());
    expect(useRunStore.getState().tokens).toBe('');
  });
  it('restores an active run snapshot including pending approval for a selected session', async () => {
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.restore('pending-run');
    });
    expect(useRunStore.getState().run).toMatchObject({
      run_id: 'pending-run',
      status: 'waiting_approval',
    });
    expect(useRunStore.getState().run?.pending_approvals).toHaveLength(1);
  });

  it('clears a stale local run when the session has no active run', async () => {
    const { result } = renderHook(() => useRunStream('s1'));
    act(() => {
      useRunStore.getState().setRun({
        run_id: 'stale-run',
        session_id: 's1',
        objective: 'stale',
        path: 'structured',
        status: 'running_structured',
        steps: {},
        pending_approvals: [],
        revision: 2,
      });
    });

    await act(async () => {
      await result.current.restore(null);
    });

    expect(useRunStore.getState().run).toBeNull();
    expect(result.current.transport).toBe('idle');
  });

  it('does not let a late restore overwrite the newly selected session', async () => {
    let release!: (value: unknown) => void;
    mocks.getRun.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const { result, rerender } = renderHook(({ sessionId }) => useRunStream(sessionId), {
      initialProps: { sessionId: 's1' },
    });
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.restore('old-run');
    });
    rerender({ sessionId: 's2' });
    release({
      run_id: 'old-run',
      session_id: 's1',
      objective: 'old',
      path: 'fast',
      status: 'completed',
      steps: {},
      pending_approvals: [],
      revision: 1,
    });
    await act(async () => {
      await pending;
    });
    expect(useRunStore.getState().run).toBeNull();
  });

  it('uploads attachments and submits their real artifact ids with selected skills', async () => {
    mocks.uploadArtifact.mockResolvedValue({
      artifact_id: 'artifact-1',
      sha256: 'sha',
      media_type: 'text/plain',
      bytes: 1,
    });
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: '1', type: 'run.completed', data: {} };
    });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.start('inspect', [new File(['x'], 'input.txt')], ['quality'], true);
    });
    expect(mocks.createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'expert',
        requested_skills: ['quality'],
        artifact_ids: ['artifact-1'],
      }),
    );
  });

  it('surfaces upload failures without creating a run', async () => {
    mocks.uploadArtifact.mockRejectedValue(new Error('附件上传失败'));
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await expect(
        result.current.start('inspect', [new File(['x'], 'input.txt')], []),
      ).rejects.toThrow('附件上传失败');
    });
    expect(result.current.transport).toBe('error');
    expect(result.current.error).toBe('附件上传失败');
    expect(mocks.createRun).not.toHaveBeenCalled();
  });

  it('cancels the active run and projects the cancelled snapshot', async () => {
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: 'streaming', type: 'token.delta', data: { delta: '' } };
      await new Promise(() => undefined);
    });
    mocks.cancelRun.mockResolvedValue({
      run_id: 'r1',
      session_id: 's1',
      objective: 'x',
      path: 'fast',
      status: 'cancelled',
      steps: {},
      pending_approvals: [],
      revision: 2,
    });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.start('x', [], []);
    });
    await act(async () => {
      await result.current.cancel();
    });
    expect(mocks.cancelRun).toHaveBeenCalledWith('r1');
    expect(useRunStore.getState().run?.status).toBe('cancelled');
  });

  it('submits approval with the snapshot revision and reconnects the stream', async () => {
    mocks.resolveApproval.mockResolvedValue({
      run_id: 'pending-run',
      session_id: 's1',
      objective: 'restored',
      path: 'structured',
      status: 'running_structured',
      steps: {},
      pending_approvals: [],
      revision: 3,
    });
    mocks.streamRun.mockImplementationOnce(async function* () {
      yield { event_id: 'done', type: 'run.completed', data: { final_text: 'done' } };
    });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.restore('pending-run');
    });
    await act(async () => {
      await result.current.approve('a1', false, 2);
    });
    expect(mocks.resolveApproval).toHaveBeenCalledWith('pending-run', 'a1', false, 2);
    await vi.waitFor(() =>
      expect(mocks.streamRun).toHaveBeenCalledWith(
        'pending-run',
        undefined,
        expect.any(AbortSignal),
      ),
    );
  });

  it('retires the approval as soon as it is submitted, without waiting on the request', async () => {
    // 确认是人已经做完的动作。等写入跑完再更新界面，就是「点了没反应」。
    let release: (snapshot: unknown) => void = () => undefined;
    mocks.resolveApproval.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    mocks.streamRun.mockImplementation(async function* () {
      yield { event_id: 'done', type: 'token.delta', data: { delta: 'A' } };
    });
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.restore('pending-run');
    });

    let submitted: Promise<void> = Promise.resolve();
    await act(async () => {
      submitted = result.current.approve('a1', true, 2);
    });
    expect(useRunStore.getState().resuming).toEqual({ approvalId: 'a1', approved: true });
    expect(mocks.resolveApproval).toHaveBeenCalledWith('pending-run', 'a1', true, 2);

    await act(async () => {
      release({
        run_id: 'pending-run',
        session_id: 's1',
        objective: 'restored',
        path: 'structured',
        status: 'running_structured',
        steps: {},
        pending_approvals: [],
        revision: 3,
      });
      await submitted;
    });
    expect(useRunStore.getState().resuming).toEqual({ approvalId: 'a1', approved: true });
  });

  it('keeps a pending approval intact when the revision request fails', async () => {
    mocks.resolveApproval.mockRejectedValue(new Error('stale approval'));
    const { result } = renderHook(() => useRunStream('s1'));
    await act(async () => {
      await result.current.restore('pending-run');
    });
    await act(async () => {
      await expect(result.current.approve('a1', true, 1)).rejects.toThrow('stale approval');
    });
    expect(useRunStore.getState().run?.status).toBe('waiting_approval');
    expect(useRunStore.getState().run?.pending_approvals).toHaveLength(1);
    expect(useRunStore.getState().resuming).toBeUndefined();
  });
});
