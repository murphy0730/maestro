import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, CheckCircle2, Copy, Database, RefreshCw, XCircle } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { getRunDebug, replaySession, type ReplayReport, type RuntimeDebugResponse } from '@/api';

const panel = 'rounded-lg border border-border-subtle bg-surface-1 shadow-sm';

export function RuntimeDebug() {
  const { runId = '' } = useParams();
  const [debug, setDebug] = useState<RuntimeDebugResponse>();
  const [replay, setReplay] = useState<ReplayReport>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    const aborter = new AbortController();
    setError(undefined);
    void getRunDebug(runId, aborter.signal)
      .then(async (result) => {
        setDebug(result);
        setReplay(await replaySession(result.run.session_id, aborter.signal));
      })
      .catch((cause) => {
        if (!aborter.signal.aborted)
          setError(cause instanceof Error ? cause.message : '运行调试数据加载失败');
      });
    return () => aborter.abort();
  }, [runId]);

  const tokenRows = useMemo(
    () =>
      debug?.context_manifests.map((manifest) => ({
        turn: String(manifest.turn_id ?? ''),
        estimated: Number(manifest.estimated_prompt_tokens ?? 0),
        breakdown: manifest.token_breakdown as Record<string, number> | undefined,
        hash: String(manifest.context_hash ?? ''),
      })) ?? [],
    [debug],
  );

  return (
    <main className="h-full overflow-y-auto bg-bg-base px-[24px] py-[20px] text-text-primary">
      <div className="mx-auto max-w-[1320px]">
        <header className="mb-[18px] flex items-center gap-[12px] border-b border-border-subtle pb-[16px]">
          <Link to="/" className="grid h-[32px] w-[32px] place-items-center rounded-md border border-border-subtle text-text-secondary hover:text-accent" aria-label="返回工作区">
            <ArrowLeft size={15} />
          </Link>
          <div>
            <p className="hud-label m-0 text-accent">RUNTIME V2 · TRAJECTORY INSPECTOR</p>
            <h1 className="m-0 mt-[3px] text-[20px] font-semibold">运行轨迹调试</h1>
          </div>
          {debug && (
            <div className="ml-auto text-right font-mono text-[10px] text-text-tertiary">
              <div>{debug.run.run_id}</div>
              <div>{debug.run.status} · revision {debug.run.revision}</div>
            </div>
          )}
        </header>

        {error && <div className={`${panel} p-[16px] text-status-error`}>{error}</div>}
        {!debug && !error && <div className={`${panel} p-[24px] text-text-tertiary`}>正在读取 durable trajectory…</div>}
        {debug && (
          <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(300px,.65fr)] gap-[16px] max-lg:grid-cols-1">
            <section className={`${panel} min-w-0 overflow-hidden`}>
              <div className="flex items-center border-b border-border-subtle px-[16px] py-[12px]">
                <h2 className="hud-label m-0 text-text-tertiary">AGENT EVENT STREAM · {debug.events.length}</h2>
              </div>
              <ol className="m-0 max-h-[680px] list-none overflow-auto p-0">
                {debug.events.map((event) => (
                  <li key={event.event_id} className="grid grid-cols-[54px_180px_1fr] gap-[10px] border-b border-border-subtle px-[16px] py-[10px] font-mono text-[10px] last:border-0 max-md:grid-cols-[44px_1fr]">
                    <span className="text-text-tertiary">#{event.sequence}</span>
                    <span className="text-accent">{event.event_type}</span>
                    <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words text-text-secondary max-md:col-span-2">{JSON.stringify(event.payload, null, 2)}</pre>
                  </li>
                ))}
              </ol>
            </section>

            <div className="space-y-[16px]">
              <section className={`${panel} p-[16px]`}>
                <h2 className="hud-label mb-[12px] flex items-center gap-[7px] text-text-tertiary"><RefreshCw size={12} /> REPLAY INTEGRITY</h2>
                {replay ? (
                  <>
                    <p className={`m-0 flex items-center gap-[7px] text-body-sm ${replay.valid ? 'text-status-success' : 'text-status-error'}`}>
                      {replay.valid ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                      {replay.valid ? '事件序列与冻结前缀一致' : '检测到 replay 不一致'}
                    </p>
                    <dl className="mt-[12px] grid grid-cols-[92px_1fr] gap-y-[5px] font-mono text-[10px] text-text-secondary">
                      <dt>last sequence</dt><dd className="m-0">{replay.last_sequence}</dd>
                      <dt>checkpoint</dt><dd className="m-0 truncate">{replay.checkpoint_id ?? 'none'}</dd>
                      <dt>context hashes</dt><dd className="m-0">{replay.context_hashes.length}</dd>
                    </dl>
                    {replay.errors.map((item) => <p key={item} className="mb-0 text-caption text-status-error">{item}</p>)}
                  </>
                ) : <span className="text-caption text-text-tertiary">校验中…</span>}
              </section>

              <section className={`${panel} p-[16px]`}>
                <h2 className="hud-label mb-[12px] flex items-center gap-[7px] text-text-tertiary"><Database size={12} /> CHECKPOINT</h2>
                <JsonBlock value={debug.checkpoint} />
              </section>

              <section className={`${panel} p-[16px]`}>
                <h2 className="hud-label mb-[12px] text-text-tertiary">CONTEXT TOKEN BUDGET</h2>
                <div className="space-y-[10px]">
                  {tokenRows.map((row) => (
                    <div key={row.turn} className="rounded-md bg-surface-2 p-[10px] font-mono text-[10px]">
                      <div className="flex justify-between text-text-primary"><span>{row.turn.slice(0, 8)}</span><span>{row.estimated} tok</span></div>
                      <div className="mt-[4px] text-text-tertiary">{Object.entries(row.breakdown ?? {}).map(([key, value]) => `${key}:${value}`).join(' · ')}</div>
                      <div className="mt-[4px] truncate text-text-tertiary" title={row.hash}>{row.hash}</div>
                    </div>
                  ))}
                  {tokenRows.length === 0 && <span className="text-caption text-text-tertiary">尚无 model turn</span>}
                </div>
              </section>

              <section className={`${panel} p-[16px]`}>
                <h2 className="hud-label mb-[12px] text-text-tertiary">PLAN / APPROVALS</h2>
                <JsonBlock value={{ plan: debug.plan, approvals: debug.approvals }} />
              </section>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  return (
    <div className="relative">
      <button type="button" aria-label="复制 JSON" onClick={() => void navigator.clipboard?.writeText(text)} className="absolute right-[6px] top-[6px] text-text-tertiary hover:text-accent"><Copy size={12} /></button>
      <pre className="m-0 max-h-[260px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-surface-2 p-[10px] pr-[26px] font-mono text-[10px] leading-relaxed text-text-secondary">{text}</pre>
    </div>
  );
}
