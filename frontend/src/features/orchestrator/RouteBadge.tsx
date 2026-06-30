import { Terminal } from 'lucide-react';
import type { RouteEngine } from '@/types';
import { ROUTE_META } from '@/lib/routes';

/**
 * RouteBadge — the routing decision card shown above an agent turn. Carries
 * the engine family color, a confidence meter (+ reason), or a zero-ambiguity
 * slash-direct variant when the user named the engine explicitly.
 * Pure presentational: all state comes from props.
 */
interface RouteBadgeProps {
  route: RouteEngine;
  confidence?: number;
  reason?: string;
  slash?: boolean;
  slashCmd?: string;
}

function ConfidenceMeter({ value, route }: { value: number; route: RouteEngine }) {
  const meta = ROUTE_META[route];
  const pct = Math.round(value * 100);
  const low = value < 0.6;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="inline-flex flex-col items-end gap-[3px]">
        <span className="text-[9.5px] font-semibold uppercase tracking-eyebrow text-text-tertiary">置信度</span>
        <span className="h-[5px] w-[52px] overflow-hidden rounded-pill border border-border-subtle bg-surface-inset">
          <span
            className={`block h-full rounded-pill ${meta.dot} ${low ? '' : meta.glow}`}
            style={{ width: `${pct}%` }}
          />
        </span>
      </span>
      <span className={`min-w-[34px] text-right font-mono text-mono font-semibold ${meta.fg}`}>{value.toFixed(2)}</span>
    </span>
  );
}

export function RouteBadge({ route, confidence, reason, slash = false, slashCmd = '/排产' }: RouteBadgeProps) {
  const meta = ROUTE_META[route];
  return (
    <div className={`flex flex-col gap-2 rounded-md border border-l-2 px-[13px] py-[10px] ${meta.tintBg} ${meta.border} ${meta.leftBorder}`}>
      <div className="flex items-center gap-[9px]">
        <span className={`h-[9px] w-[9px] flex-none rounded-full ${meta.dot} ${meta.glow}`} />
        <span className={`text-body-sm font-semibold tracking-mono ${meta.fg}`}>{meta.zh}</span>
        <span className="font-mono text-[11px] tracking-wide text-text-tertiary">{meta.en}</span>
        <span className="flex-1" />
        {slash ? (
          <span
            className={`inline-flex h-6 items-center gap-[6px] rounded-pill border bg-surface-inset px-[10px] font-mono text-mono-sm font-semibold ${meta.border} ${meta.fg}`}
          >
            <Terminal size={12} strokeWidth={2} />
            {slashCmd} · 直达
          </span>
        ) : (
          confidence != null && <ConfidenceMeter value={confidence} route={route} />
        )}
      </div>
      {reason && (
        <div className="flex gap-[7px] pl-[18px]">
          <span className="flex-none pt-[1px] text-[10px] font-semibold uppercase tracking-[0.08em] text-text-tertiary">理由</span>
          <span className="text-caption leading-snug text-text-secondary">{reason}</span>
        </div>
      )}
    </div>
  );
}
