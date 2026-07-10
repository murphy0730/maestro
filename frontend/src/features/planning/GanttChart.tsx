import { useMemo } from 'react';
import type { GanttData, GanttTaskType } from '@/types/api';

/**
 * GanttChart — resource rows × an hourly time axis, laid out with CSS Grid.
 * No charting library: bars are absolutely positioned by percentage of the
 * run's time window, so the whole thing reflows with its container.
 *
 * Colour is not decoration here — it is a direct projection of
 * `GanttTask.type`, and the legend names each mapping. Changeover is hatched
 * as well as orange: it is a transition, not output.
 */
const TASK_STYLE: Record<GanttTaskType, { bar: string; swatch: string; label: string }> = {
  production: {
    bar: 'bg-planning-bg border-planning-border text-planning-fg',
    swatch: 'bg-planning-bg border-planning-border',
    label: '生产',
  },
  changeover: {
    bar: 'border-scheduling-border text-scheduling-fg bg-scheduling-bg bg-[repeating-linear-gradient(45deg,transparent_0_4px,var(--surface-1)_4px_8px)]',
    swatch:
      'border-scheduling-border bg-scheduling-bg bg-[repeating-linear-gradient(45deg,transparent_0_3px,var(--surface-1)_3px_6px)]',
    label: '换型',
  },
  downtime: {
    bar: 'bg-surface-3 border-border-default text-text-tertiary',
    swatch: 'bg-surface-3 border-border-default',
    label: '停机',
  },
  shortage: {
    bar: 'bg-status-error-bg border-status-error/40 text-status-error',
    swatch: 'bg-status-error-bg border-status-error/40',
    label: '缺料',
  },
};

const HOUR_MS = 3_600_000;

interface GanttChartProps {
  data: GanttData;
  title?: string;
  /** Position of the "now" marker. Omit to hide it. */
  now?: Date;
}

export function GanttChart({ data, title, now }: GanttChartProps) {
  const axis = useMemo(() => {
    const stamps = data.tasks.flatMap((t) => [
      new Date(t.start).getTime(),
      new Date(t.end).getTime(),
    ]);
    if (stamps.length === 0) return null;
    // Snap the axis to whole hours so tick labels line up with the grid lines.
    const start = Math.floor(Math.min(...stamps) / HOUR_MS) * HOUR_MS;
    const end = Math.ceil(Math.max(...stamps) / HOUR_MS) * HOUR_MS;
    const hours = Math.max(1, Math.round((end - start) / HOUR_MS));
    return { start, hours, span: end - start };
  }, [data.tasks]);

  if (!axis) {
    return (
      <div className="rounded-lg border border-border-subtle bg-surface-1 p-6 text-center text-body-sm text-text-tertiary">
        本次求解没有产生任何排程任务。
      </div>
    );
  }

  const pct = (ms: number) => ((ms - axis.start) / axis.span) * 100;
  const nowPct = now ? pct(now.getTime()) : null;
  const nowVisible = nowPct !== null && nowPct >= 0 && nowPct <= 100;

  return (
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-1">
      <div className="flex flex-wrap items-center gap-[10px] border-b border-border-subtle px-[14px] py-[11px]">
        <span className="font-display text-body-sm font-medium text-text-primary">
          {title ?? '资源甘特'}
        </span>
        <div className="ml-auto flex flex-wrap gap-3 text-caption text-text-tertiary">
          {(Object.keys(TASK_STYLE) as GanttTaskType[]).map((type) => (
            <span key={type} className="inline-flex items-center gap-[5px]">
              <i
                className={`h-[9px] w-[9px] flex-none rounded-xs border ${TASK_STYLE[type].swatch}`}
              />
              {TASK_STYLE[type].label}
            </span>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[780px]">
          {/* Hour axis */}
          <div
            className="grid border-b border-border-subtle bg-surface-2"
            style={{ gridTemplateColumns: `118px repeat(${axis.hours}, 1fr)` }}
          >
            <div className="px-3 py-[6px] text-micro font-medium uppercase text-text-tertiary">
              资源
            </div>
            {Array.from({ length: axis.hours }, (_, i) => (
              <div
                key={i}
                className="border-l border-border-subtle py-[6px] text-center font-mono text-[10.5px] text-text-tertiary"
              >
                {new Date(axis.start + i * HOUR_MS).getHours().toString().padStart(2, '0')}
              </div>
            ))}
          </div>

          {data.resources.map((res) => {
            const tasks = data.tasks.filter((t) => t.resource_id === res.id);
            return (
              <div
                key={res.id}
                className="grid border-b border-border-subtle last:border-b-0"
                style={{ gridTemplateColumns: '118px 1fr' }}
              >
                <div className="flex flex-col justify-center border-r border-border-subtle px-3 py-2">
                  <span className="text-body-sm font-medium text-text-primary">{res.name}</span>
                  <span className="font-mono text-[10.5px] text-text-tertiary">{res.id}</span>
                </div>
                <div
                  className="relative h-11"
                  style={{
                    backgroundImage:
                      'linear-gradient(to right, var(--border-subtle) 0 1px, transparent 1px)',
                    backgroundSize: `calc(100% / ${axis.hours}) 100%`,
                  }}
                >
                  {nowVisible && (
                    <div
                      aria-hidden="true"
                      className="absolute inset-y-0 w-px bg-accent opacity-80"
                      style={{ left: `${nowPct}%` }}
                    />
                  )}
                  {tasks.map((t) => {
                    const left = pct(new Date(t.start).getTime());
                    const width = pct(new Date(t.end).getTime()) - left;
                    const s = TASK_STYLE[t.type];
                    return (
                      <div
                        key={t.id}
                        title={`${t.label} · ${t.order_id}`}
                        className={`absolute top-[7px] flex h-[30px] items-center overflow-hidden whitespace-nowrap rounded-xs border px-2 font-mono text-[10.5px] font-medium ${s.bar}`}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      >
                        {t.label}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
