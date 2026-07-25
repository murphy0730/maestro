import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadArtifact } from './artifacts';
import { cancelRun, createRun, getRun, resolveApproval, streamRun } from './runs';
import { useRunStore } from '@/stores/runStore';
import type { RunStatus } from '@/types/api/runs';

const terminal = new Set<RunStatus>(['completed', 'failed', 'cancelled']);
const retryDelays = [100, 300, 900];
const wait = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export function useRunStream(sessionId: string) {
  const apply = useRunStore((state) => state.apply);
  const setRun = useRunStore((state) => state.setRun);
  const mergeRun = useRunStore((state) => state.mergeRun);
  const diagnose = useRunStore((state) => state.diagnose);
  const reset = useRunStore((state) => state.reset);
  const markRecovered = useRunStore((state) => state.markRecovered);
  const [transport, setTransport] = useState<'idle' | 'connecting' | 'streaming' | 'uploading' | 'error'>('idle');
  const [error, setError] = useState<string>();
  const controller = useRef<AbortController>();
  const lastEventId = useRef<string>();
  const activeRun = useRef<string>();
  const seenEventIds = useRef(new Set<string>());
  const generation = useRef(0);

  const connect = useCallback(async (runId: string) => {
    controller.current?.abort();
    const aborter = new AbortController();
    controller.current = aborter;
    activeRun.current = runId;
    setError(undefined);
    setTransport('connecting');
    for (let attempt = 0; attempt <= retryDelays.length && !aborter.signal.aborted; attempt += 1) {
      try {
        for await (const frame of streamRun(runId, lastEventId.current, aborter.signal)) {
          if ('unknown' in frame) { diagnose(`Ignored unknown event ${frame.type}`); continue; }
          if (frame.event_id) {
            lastEventId.current = frame.event_id;
            if (seenEventIds.current.has(frame.event_id)) continue;
            seenEventIds.current.add(frame.event_id);
          }
          apply(frame);
          setError(undefined);
          if (frame.type === 'approval.requested') mergeRun(await getRun(runId));
          setTransport('streaming');
        }
        const status = useRunStore.getState().run?.status;
        if (terminal.has(status ?? 'failed') || status === 'waiting_approval' || status === 'reconciling' || status === 'waiting_external') { setError(undefined); setTransport('idle'); return; }
      } catch (cause) {
        if (aborter.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : '运行流连接失败');
      }
      if (attempt === retryDelays.length) break;
      await wait(retryDelays[attempt]);
    }
    if (!aborter.signal.aborted) setTransport('error');
  }, [apply, diagnose, mergeRun]);

  const start = useCallback(async (message: string, files: File[], skillNames: string[], expert = false) => {
    const currentGeneration = generation.current;
    reset(); lastEventId.current = undefined; seenEventIds.current.clear();
    setError(undefined);
    try {
      if (files.length > 0) setTransport('uploading');
      const artifacts = await Promise.all(files.map(uploadArtifact));
      if (currentGeneration !== generation.current) throw new DOMException('Session changed', 'AbortError');
      setTransport('connecting');
      const run = await createRun({ session_id: sessionId, message, source: expert ? 'expert' : 'chat', skill_names: skillNames, artifact_ids: artifacts.map((artifact) => artifact.artifact_id) });
      if (currentGeneration !== generation.current) throw new DOMException('Session changed', 'AbortError');
      setRun(run); void connect(run.run_id); return run;
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
      setTransport('error');
      setError(cause instanceof Error ? cause.message : '任务创建失败');
      throw cause;
    }
  }, [connect, reset, sessionId, setRun]);
  const approve = useCallback(async (approvalId: string, approved: boolean, revision: number) => {
    const runId = activeRun.current;
    const currentGeneration = generation.current;
    if (!runId) return;
    const snapshot = await resolveApproval(runId, approvalId, approved, revision);
    if (currentGeneration !== generation.current || activeRun.current !== runId) return;
    mergeRun(snapshot);
    void connect(runId);
  }, [connect, mergeRun]);
  const cancel = useCallback(async () => {
    const runId = activeRun.current;
    const currentGeneration = generation.current;
    if (!runId) return;
    const snapshot = await cancelRun(runId);
    if (currentGeneration !== generation.current || activeRun.current !== runId) return;
    mergeRun(snapshot);
  }, [mergeRun]);
  const restore = useCallback(async (runId?: string | null) => {
    if (!runId) return;
    const currentGeneration = generation.current;
    lastEventId.current = undefined; seenEventIds.current.clear(); activeRun.current = runId;
    const run = await getRun(runId);
    if (currentGeneration !== generation.current || activeRun.current !== runId) return;
    setRun(run);
    markRecovered();
    if (!terminal.has(run.status) && !['waiting_approval', 'reconciling', 'waiting_external'].includes(run.status)) void connect(runId);
  }, [connect, markRecovered, setRun]);
  useEffect(() => {
    generation.current += 1;
    controller.current?.abort();
    activeRun.current = undefined;
    lastEventId.current = undefined;
    seenEventIds.current.clear();
    reset();
  }, [reset, sessionId]);
  useEffect(() => () => controller.current?.abort(), []);
  return { start, approve, cancel, restore, transport, error, reconnect: () => activeRun.current ? connect(activeRun.current) : Promise.resolve() };
}
