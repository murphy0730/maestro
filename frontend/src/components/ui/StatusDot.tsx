/**
 * StatusDot — 设计系统 v2 的 `.dot`：6px 发光状态点。
 * 只作为文字状态的视觉补充，never 单独承载信息。
 */
export type DotTone = 'accent' | 'success' | 'warning' | 'danger' | 'controlled' | 'muted';

const TONES: Record<DotTone, string> = {
  accent: 'bg-accent shadow-[0_0_8px_var(--accent)]',
  success: 'bg-status-success shadow-[0_0_8px_var(--status-success)]',
  warning: 'bg-auth-confirm shadow-[0_0_8px_var(--auth-confirm)]',
  danger: 'bg-status-error shadow-[0_0_8px_var(--status-error)]',
  controlled: 'bg-path-controlled shadow-[0_0_8px_var(--path-controlled)]',
  muted: 'bg-text-tertiary',
};

interface StatusDotProps {
  tone?: DotTone;
  /** 运行中 / 等待确认等活跃状态才脉冲；reduced-motion 下由全局规则关闭。 */
  pulse?: boolean;
  size?: number;
  className?: string;
}

export function StatusDot({
  tone = 'muted',
  pulse = false,
  size = 6,
  className = '',
}: StatusDotProps) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={`inline-block flex-none rounded-full ${TONES[tone]} ${pulse ? 'dot-pulse' : ''} ${className}`}
    />
  );
}
