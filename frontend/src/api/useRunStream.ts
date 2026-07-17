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
  const reset = useRunStore((state) => state.reset);
  const [transport, setTransport] = useState<'idle' | 'connecting' | 'streaming' | 'error'>('idle');
  const controller = useRef<AbortController>();
  const lastEventId = useRef<string>();
  const activeRun = useRef<string>();
  const seenEventIds = useRef(new Set<string>());

  const connect = useCallback(async (runId: string) => {
    controller.current?.abort();
    const aborter = new AbortController();
    controller.current = aborter;
    activeRun.current = runId;
    setTransport('connecting');
    for (let attempt = 0; attempt <= retryDelays.length && !aborter.signal.aborted; attempt += 1) {
      try {
        for await (const frame of streamRun(runId, lastEventId.current, aborter.signal)) {
          if (frame.id) {
            lastEventId.current = frame.id;
            if (seenEventIds.current.has(frame.id)) continue;
            seenEventIds.current.add(frame.id);
          }
          apply({ event_id: frame.id, type: frame.event, data: frame.data });
          if (frame.event === 'approval.requested') mergeRun(await getRun(runId));
          setTransport('streaming');
        }
        if (terminal.has(useRunStore.getState().run?.status ?? 'failed')) { setTransport('idle'); return; }
      } catch {
        if (aborter.signal.aborted) return;
      }
      if (attempt === retryDelays.length) break;
      await wait(retryDelays[attempt]);
    }
    if (!aborter.signal.aborted) setTransport('error');
  }, [apply, mergeRun]);

  const start = useCallback(async (message: string, files: File[], skillNames: string[], expert = false) => {
    reset(); lastEventId.current = undefined; seenEventIds.current.clear();
    const artifacts = await Promise.all(files.map(uploadArtifact));
    const run = await createRun({ session_id: sessionId, message, source: expert ? 'expert' : 'chat', skill_names: skillNames, artifact_ids: artifacts.map((artifact) => artifact.artifact_id) });
    setRun(run); void connect(run.run_id); return run;
  }, [connect, reset, sessionId, setRun]);
  const approve = useCallback(async (approvalId: string, approved: boolean, revision: number) => { if (!activeRun.current) return; mergeRun(await resolveApproval(activeRun.current, approvalId, approved, revision)); }, [mergeRun]);
  const cancel = useCallback(async () => { if (!activeRun.current) return; mergeRun(await cancelRun(activeRun.current)); }, [mergeRun]);
  useEffect(() => () => controller.current?.abort(), []);
  return { start, approve, cancel, transport };
}
