import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadArtifact } from './artifacts';
import { cancelRun, createRun, getRun, resolveApproval, streamRun } from './runs';
import { useRunStore } from '@/stores/runStore';
import type { RunStatus } from '@/types/api/runs';

const terminal = new Set<RunStatus>(['completed', 'failed', 'cancelled']);
const streamSettled = (status?: RunStatus) =>
  Boolean(
    status &&
      (terminal.has(status) ||
        ['waiting_approval', 'reconciling', 'waiting_external'].includes(status)),
  );
const retryDelays = [100, 300, 900];
const reconcileIntervalMs = 2_000;
const wait = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export function useRunStream(sessionId: string) {
  const apply = useRunStore((state) => state.apply);
  const setRun = useRunStore((state) => state.setRun);
  const mergeRun = useRunStore((state) => state.mergeRun);
  const diagnose = useRunStore((state) => state.diagnose);
  const reset = useRunStore((state) => state.reset);
  const markRecovered = useRunStore((state) => state.markRecovered);
  const markApprovalSubmitted = useRunStore((state) => state.markApprovalSubmitted);
  const clearResuming = useRunStore((state) => state.clearResuming);
  const [transport, setTransport] = useState<
    'idle' | 'connecting' | 'streaming' | 'uploading' | 'error'
  >('idle');
  const [error, setError] = useState<string>();
  const controller = useRef<AbortController>();
  const lastEventId = useRef<string>();
  const activeRun = useRef<string>();
  const seenEventIds = useRef(new Set<string>());
  const generation = useRef(0);

  const connect = useCallback(
    async (runId: string) => {
      const currentGeneration = generation.current;
      controller.current?.abort();
      const aborter = new AbortController();
      controller.current = aborter;
      activeRun.current = runId;
      setError(undefined);
      setTransport('connecting');
      let reconciliationInFlight = false;
      const reconcileSnapshot = async () => {
        if (reconciliationInFlight || aborter.signal.aborted) return;
        reconciliationInFlight = true;
        try {
          const snapshot = await getRun(runId);
          if (
            aborter.signal.aborted ||
            currentGeneration !== generation.current ||
            activeRun.current !== runId
          )
            return;
          mergeRun(snapshot);
          if (streamSettled(snapshot.status)) {
            setError(undefined);
            setTransport('idle');
            aborter.abort();
          }
        } catch {
          // SSE remains the primary transport; a transient snapshot failure is retried by this timer.
        } finally {
          reconciliationInFlight = false;
        }
      };
      const reconciliationTimer = window.setInterval(
        () => void reconcileSnapshot(),
        reconcileIntervalMs,
      );
      try {
        for (
          let attempt = 0;
          attempt <= retryDelays.length && !aborter.signal.aborted;
          attempt += 1
        ) {
          try {
            for await (const frame of streamRun(runId, lastEventId.current, aborter.signal)) {
              if (frame.unknown) {
                diagnose(`Ignored unknown event ${frame.event_type ?? frame.type ?? 'unknown'}`);
                continue;
              }
              if (frame.event_id) {
                lastEventId.current = frame.event_id;
                if (seenEventIds.current.has(frame.event_id)) continue;
                seenEventIds.current.add(frame.event_id);
              }
              apply(frame);
              setError(undefined);
              if ((frame.event_type ?? frame.type) === 'APPROVAL_REQUESTED')
                mergeRun(await getRun(runId));
              setTransport('streaming');
            }
            await reconcileSnapshot();
            const status = useRunStore.getState().run?.status;
            if (streamSettled(status)) {
              setError(undefined);
              setTransport('idle');
              return;
            }
          } catch (cause) {
            if (aborter.signal.aborted) return;
            setError(cause instanceof Error ? cause.message : '运行流连接失败');
          }
          if (attempt === retryDelays.length) break;
          await wait(retryDelays[attempt]);
        }
        await reconcileSnapshot();
        if (!aborter.signal.aborted) setTransport('error');
      } finally {
        window.clearInterval(reconciliationTimer);
      }
    },
    [apply, diagnose, mergeRun],
  );

  const start = useCallback(
    async (message: string, files: File[], skillNames: string[], expert = false) => {
      const currentGeneration = generation.current;
      reset();
      lastEventId.current = undefined;
      seenEventIds.current.clear();
      setError(undefined);
      try {
        if (files.length > 0) setTransport('uploading');
        const artifacts = await Promise.all(files.map(uploadArtifact));
        if (currentGeneration !== generation.current)
          throw new DOMException('Session changed', 'AbortError');
        setTransport('connecting');
        const run = await createRun({
          session_id: sessionId,
          message,
          source: expert ? 'expert' : 'chat',
          requested_skills: skillNames,
          artifact_ids: artifacts.map((artifact) => artifact.artifact_id),
        });
        if (currentGeneration !== generation.current)
          throw new DOMException('Session changed', 'AbortError');
        setRun(run);
        void connect(run.run_id);
        return run;
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
        setTransport('error');
        setError(cause instanceof Error ? cause.message : '任务创建失败');
        throw cause;
      }
    },
    [connect, reset, sessionId, setRun],
  );
  const approve = useCallback(
    async (approvalId: string, approved: boolean, revision: number) => {
      const runId = activeRun.current;
      const currentGeneration = generation.current;
      if (!runId) return;
      // 先切到恢复态：确认是人做完的动作，界面不该继续摆着一张等人的卡片。
      markApprovalSubmitted(approvalId, approved);
      try {
        await resolveApproval(runId, approvalId, approved, revision);
        if (currentGeneration !== generation.current || activeRun.current !== runId) return;
        // 审批后的执行在后端后台恢复；等快照先离开 waiting_approval 再重连，
        // 否则一个过早的 SSE 会按“暂停态”立即关闭。
        for (let attempt = 0; attempt < 40; attempt += 1) {
          const snapshot = await getRun(runId);
          if (currentGeneration !== generation.current || activeRun.current !== runId) return;
          mergeRun(snapshot);
          if (snapshot.status !== 'waiting_approval') break;
          await wait(50);
        }
        void connect(runId);
      } catch (cause) {
        if (currentGeneration === generation.current && activeRun.current === runId)
          clearResuming();
        throw cause;
      }
    },
    [clearResuming, connect, markApprovalSubmitted, mergeRun],
  );
  const cancel = useCallback(async () => {
    const runId = activeRun.current;
    const currentGeneration = generation.current;
    if (!runId) return;
    const snapshot = await cancelRun(runId);
    if (currentGeneration !== generation.current || activeRun.current !== runId) return;
    mergeRun(snapshot);
  }, [mergeRun]);
  const restore = useCallback(
    async (runId?: string | null) => {
      if (!runId) {
        controller.current?.abort();
        activeRun.current = undefined;
        lastEventId.current = undefined;
        seenEventIds.current.clear();
        reset();
        setError(undefined);
        setTransport('idle');
        return;
      }
      const currentGeneration = generation.current;
      lastEventId.current = undefined;
      seenEventIds.current.clear();
      activeRun.current = runId;
      const run = await getRun(runId);
      if (currentGeneration !== generation.current || activeRun.current !== runId) return;
      setRun(run);
      markRecovered();
      if (
        !terminal.has(run.status) &&
        !['waiting_approval', 'reconciling', 'waiting_external'].includes(run.status)
      )
        void connect(runId);
    },
    [connect, markRecovered, reset, setRun],
  );
  useEffect(() => {
    generation.current += 1;
    controller.current?.abort();
    activeRun.current = undefined;
    lastEventId.current = undefined;
    seenEventIds.current.clear();
    reset();
  }, [reset, sessionId]);
  useEffect(() => () => controller.current?.abort(), []);
  return {
    start,
    approve,
    cancel,
    restore,
    transport,
    error,
    reconnect: () => (activeRun.current ? connect(activeRun.current) : Promise.resolve()),
  };
}
