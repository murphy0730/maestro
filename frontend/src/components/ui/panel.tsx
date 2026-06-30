import type { ReactNode } from 'react';
import { CheckCircle2, Info } from 'lucide-react';
import type { RouteEngine } from '@/types';
import { ROUTE_META } from '@/lib/routes';

/** Shared building blocks for engine context panels. Pure presentational. */

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-[10px] flex items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-eyebrow text-text-tertiary">{children}</span>
      {right && <span className="ml-auto whitespace-nowrap">{right}</span>}
    </div>
  );
}

export function EngineStrip({ route, title, meta }: { route: RouteEngine; title: string; meta: string }) {
  const m = ROUTE_META[route];
  return (
    <div className={`flex items-center gap-3 rounded-md border border-l-2 px-[14px] py-3 ${m.tintBg} ${m.border} ${m.leftBorder}`}>
      <span className={`h-[10px] w-[10px] flex-none rounded-full ${m.dot} ${m.glow}`} />
      <div className="min-w-0 flex-1">
        <div className={`text-body-sm font-semibold ${m.fg}`}>{title}</div>
        <div className="mt-[2px] font-mono text-[10.5px] text-text-tertiary">{meta}</div>
      </div>
      <CheckCircle2 size={18} className={m.fg} />
    </div>
  );
}

/** A labeled parameter line. `changed` flags an agent-proposed edit (accent). */
export function ParamRow({
  label,
  value,
  unit,
  changed = false,
}: {
  label: string;
  value: string;
  unit?: string;
  changed?: boolean;
}) {
  return (
    <div className="flex items-center gap-[10px] border-b border-border-subtle py-2 font-sans">
      <span className="flex-1 text-body-sm text-text-secondary">{label}</span>
      <span
        className={`inline-flex items-baseline gap-1 rounded-sm border px-[9px] py-[3px] ${
          changed ? 'border-accent-border bg-accent-bg shadow-glow-accent-sm' : 'border-border-default bg-surface-inset'
        }`}
      >
        <span className={`font-mono text-mono-sm font-semibold ${changed ? 'text-accent-fg' : 'text-text-primary'}`}>
          {value}
        </span>
        {unit && <span className="text-micro text-text-tertiary">{unit}</span>}
      </span>
    </div>
  );
}

export function PanelFootNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary">
      <Info size={12} />
      {children}
    </div>
  );
}
