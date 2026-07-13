import type { RouteEngine } from '@/types';

/**
 * Per-engine presentation metadata. Class strings are written out in full
 * (not template-constructed) so Tailwind's JIT can see them. Every color
 * resolves to a token defined in tailwind.config.ts — no raw hex anywhere.
 */
export interface RouteMeta {
  zh: string;
  en: string;
  /** solid engine color, e.g. the status dot fill */
  dot: string;
  /** left accent border color */
  leftBorder: string;
  /** foreground text on dark */
  fg: string;
  /** tinted fill background */
  tintBg: string;
  /** tint border (alpha) */
  border: string;
  /** glow shadow */
  glow: string;
}

export const ROUTE_META: Record<RouteEngine, RouteMeta> = {
  planning: {
    zh: '排产',
    en: 'Planning',
    dot: 'bg-planning',
    leftBorder: 'border-l-planning',
    fg: 'text-planning-fg',
    tintBg: 'bg-planning-bg',
    border: 'border-planning-border',
    glow: 'shadow-glow-planning',
  },
  scheduling: {
    zh: '调度',
    en: 'Scheduling',
    dot: 'bg-scheduling',
    leftBorder: 'border-l-scheduling',
    fg: 'text-scheduling-fg',
    tintBg: 'bg-scheduling-bg',
    border: 'border-scheduling-border',
    glow: 'shadow-glow-scheduling',
  },
  query: {
    zh: '查询',
    en: 'Query',
    dot: 'bg-query',
    leftBorder: 'border-l-query',
    fg: 'text-query-fg',
    tintBg: 'bg-query-bg',
    border: 'border-query-border',
    glow: 'shadow-glow-query',
  },
  uncertain: {
    zh: '不确定',
    en: 'Uncertain',
    dot: 'bg-uncertain',
    leftBorder: 'border-l-uncertain',
    fg: 'text-uncertain-fg',
    tintBg: 'bg-uncertain-bg',
    border: 'border-uncertain-border',
    glow: 'shadow-glow-uncertain',
  },
  // skill 复用 accent 色族 (SkillPanel 亦用 accent，令牌已存在，无需新增设计 token)。
  skill: {
    zh: '技能',
    en: 'skill',
    dot: 'bg-accent',
    leftBorder: 'border-l-accent',
    fg: 'text-accent-fg',
    tintBg: 'bg-accent-bg',
    border: 'border-accent-border',
    glow: 'shadow-glow-accent',
  },
};
