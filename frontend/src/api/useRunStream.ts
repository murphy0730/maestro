import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadArtifact } from './artifacts';
import { cancelRun, createRun, getRun, resolveApproval, streamRun } from './runs';
import { useRunStore } from '@/stores/runStore';

export function useRunStream(sessionId: string) {
  const apply = useRunStore((state) => state.apply); const setRun = useRunStore((state) => state.setRun); const reset = useRunStore((state) => state.reset);
  const [transport, setTransport] = useState<'idle' | 'connecting' | 'streaming' | 'error'>('idle');
  const controller = useRef<AbortController>(); const lastEventId = useRef<string>(); const activeRun = useRef<string>();
  const connect = useCallback(async (runId: string) => {
    controller.current?.abort(); const aborter = new AbortController(); controller.current = aborter; activeRun.current = runId; setTransport('connecting');
    try { for await (const frame of streamRun(runId, lastEventId.current, aborter.signal)) { if (frame.id) lastEventId.current = frame.id; apply({ event_id: frame.id, type: frame.event, data: frame.data }); if (frame.event === 'approval.requested') setRun(await getRun(runId)); setTransport('streaming'); } if (!aborter.signal.aborted) setTransport('idle'); }
    catch { if (!aborter.signal.aborted) setTransport('error'); }
  }, [apply, setRun]);
  const start = useCallback(async (message: string, files: File[], skillNames: string[], expert = false) => {
    reset(); lastEventId.current = undefined; const artifacts = await Promise.all(files.map(uploadArtifact));
    const run = await createRun({ session_id: sessionId, message, source: expert ? 'expert' : 'chat', skill_names: skillNames, artifact_ids: artifacts.map((artifact) => artifact.artifact_id) });
    setRun(run); void connect(run.run_id); return run;
  }, [connect, reset, sessionId, setRun]);
  const approve = useCallback(async (approvalId: string, approved: boolean, revision: number) => { if (!activeRun.current) return; const run = await resolveApproval(activeRun.current, approvalId, approved, revision); setRun(run); }, [setRun]);
  const cancel = useCallback(async () => { if (!activeRun.current) return; const run = await cancelRun(activeRun.current); setRun(run); }, [setRun]);
  useEffect(() => () => controller.current?.abort(), []);
  return { start, approve, cancel, transport };
}
