import { useState } from 'react';
import { getObservation } from '@/api';
import type { ObservationPage, SchedulingTraceStep } from '@/types';
import { Badge } from '@/components/ui/Badge';
import { SectionLabel } from '@/components/ui/panel';

/**
 * ObservationTrace — renders the调度 ReAct 工具轨迹 (方案2). When a step's
 * observation is an offloaded handle (`observation_ref`), the full result lives
 * server-side; a "查看完整结果" button lazy-loads it via GET /observations/{ref}.
 */
function ObservationRow({ step }: { step: SchedulingTraceStep }) {
  const ref = step.observation?.observation_ref;
  const [page, setPage] = useState<ObservationPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!ref) return;
    setLoading(true);
    setError(null);
    try {
      setPage(await getObservation(ref));
    } catch {
      setError('加载失败，观察可能已过期');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mb-2 rounded-md border border-border-default bg-surface-2 px-3 py-[9px]">
      <div className="flex items-center gap-2">
        <span className="font-mono text-mono-sm font-semibold text-text-primary">{step.tool}</span>
        {step.blocked && (
          <Badge tone="warning" size="sm">
            已拦截
          </Badge>
        )}
        {typeof step.observation?.total === 'number' && (
          <span className="font-mono text-[10px] text-text-tertiary">
            {step.observation.total} 条
          </span>
        )}
      </div>
      {step.thought && (
        <div className="mt-1 text-caption leading-snug text-text-secondary">{step.thought}</div>
      )}
      {ref && !page && (
        <button
          onClick={load}
          disabled={loading}
          className="mt-[6px] inline-flex h-7 cursor-pointer items-center rounded-md border border-border-default bg-surface-1 px-[10px] text-caption font-semibold text-text-secondary disabled:opacity-60"
        >
          {loading ? '加载中…' : '查看完整结果'}
        </button>
      )}
      {error && <div className="mt-[6px] text-caption text-text-tertiary">{error}</div>}
      {page && (
        <pre className="mt-[6px] max-h-52 overflow-auto rounded-md border border-border-subtle bg-surface-1 p-2 font-mono text-[10.5px] leading-relaxed text-text-secondary">
          {JSON.stringify(page.items ?? page.keys ?? page.slice ?? page.preview, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function ObservationTrace({ steps }: { steps: SchedulingTraceStep[] }) {
  if (!steps.length) return null;
  return (
    <div>
      <SectionLabel>执行轨迹</SectionLabel>
      {steps.map((s, i) => (
        <ObservationRow key={`${s.tool}-${i}`} step={s} />
      ))}
    </div>
  );
}
