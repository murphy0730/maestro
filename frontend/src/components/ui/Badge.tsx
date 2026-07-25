import type { ReactNode } from 'react';

/**
 * Badge — 设计系统 v2 的 `.bdg`：等宽小写字距徽章，用于模式、路径、运行终态、
 * 技能信任态。色相只表达语义：青=沟通/导航，绿=执行成功，琥珀=等待确认，
 * 红=失败，紫=受控路径，蓝/橙/青绿=排产/调度/查询模式轴。
 */
export type BadgeTone =
  | 'accent'
  | 'success'
  | 'warning'
  | 'danger'
  | 'controlled'
  | 'planning'
  | 'scheduling'
  | 'query'
  | 'neutral';

const TONES: Record<BadgeTone, string> = {
  accent: 'text-accent border-accent-border bg-accent-bg',
  success: 'text-status-success border-auth-auto-border bg-status-success-bg',
  warning: 'text-auth-confirm border-auth-confirm-border bg-status-warning-bg',
  danger: 'text-status-error border-status-error/35 bg-status-error-bg',
  controlled: 'text-path-controlled border-path-controlled/35 bg-path-controlled-bg',
  planning: 'text-mode-planning border-mode-planning/35 bg-mode-planning-bg',
  scheduling: 'text-mode-scheduling border-mode-scheduling/35 bg-mode-scheduling-bg',
  query: 'text-mode-query border-mode-query/35 bg-mode-query-bg',
  neutral: 'text-text-tertiary border-border-default bg-surface-2',
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  /** 图标或状态点，渲染在文本前 —— 状态不只靠颜色传达。 */
  icon?: ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ tone = 'neutral', children, icon, className = '', title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-[6px] rounded-xs border px-[9px] py-[3px] font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.1em] ${TONES[tone]} ${className}`}
    >
      {icon}
      {children}
    </span>
  );
}
