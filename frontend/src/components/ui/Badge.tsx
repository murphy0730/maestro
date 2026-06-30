import type { ReactNode } from 'react';

/**
 * Compact status / label chip. `tone` maps to the semantic + route token
 * families; every color is a token class, none hardcoded. Pure presentational.
 */
export type BadgeTone =
  | 'neutral'
  | 'accent'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'planning'
  | 'scheduling'
  | 'query'
  | 'uncertain';

interface ToneClasses {
  text: string;
  soft: string;
  dot: string;
  glow: string;
}

const TONES: Record<BadgeTone, ToneClasses> = {
  neutral: { text: 'text-text-primary', soft: 'bg-surface-3 border-border-default', dot: 'bg-text-secondary', glow: '' },
  accent: { text: 'text-accent-fg', soft: 'bg-accent-bg border-accent-border', dot: 'bg-accent', glow: 'shadow-glow-accent-sm' },
  success: { text: 'text-status-success', soft: 'bg-status-success-bg border-status-success/40', dot: 'bg-status-success', glow: 'shadow-glow-success' },
  warning: { text: 'text-status-warning', soft: 'bg-status-warning-bg border-status-warning/40', dot: 'bg-status-warning', glow: 'shadow-glow-confirm' },
  error: { text: 'text-status-error', soft: 'bg-status-error-bg border-status-error/40', dot: 'bg-status-error', glow: '' },
  info: { text: 'text-status-info', soft: 'bg-status-info-bg border-status-info/40', dot: 'bg-status-info', glow: '' },
  planning: { text: 'text-planning-fg', soft: 'bg-planning-bg border-planning-border', dot: 'bg-planning', glow: 'shadow-glow-planning' },
  scheduling: { text: 'text-scheduling-fg', soft: 'bg-scheduling-bg border-scheduling-border', dot: 'bg-scheduling', glow: 'shadow-glow-scheduling' },
  query: { text: 'text-query-fg', soft: 'bg-query-bg border-query-border', dot: 'bg-query', glow: 'shadow-glow-query' },
  uncertain: { text: 'text-uncertain-fg', soft: 'bg-uncertain-bg border-uncertain-border', dot: 'bg-uncertain', glow: 'shadow-glow-uncertain' },
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  size?: 'sm' | 'md';
  dot?: boolean;
  mono?: boolean;
  glow?: boolean;
  className?: string;
}

export function Badge({
  children,
  tone = 'neutral',
  size = 'md',
  dot = false,
  mono = false,
  glow = false,
  className = '',
}: BadgeProps) {
  const t = TONES[tone];
  const sz = size === 'sm' ? 'h-[18px] px-2 text-micro gap-[5px]' : 'h-[22px] px-3 text-caption gap-[6px]';
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-pill border font-semibold tracking-wide ${sz} ${t.text} ${t.soft} ${
        mono ? 'font-mono tracking-mono' : 'font-sans'
      } ${glow ? t.glow : ''} ${className}`}
    >
      {dot && <span className={`h-[6px] w-[6px] flex-none rounded-full ${t.dot} ${glow ? t.glow : ''}`} />}
      {children}
    </span>
  );
}
