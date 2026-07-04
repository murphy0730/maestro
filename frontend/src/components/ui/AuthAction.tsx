import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Check, Zap } from 'lucide-react';
import type { AuthLevel } from '@/types';

/**
 * Action button whose appearance encodes its authorization level:
 * `auto` (green, executes immediately) vs `confirm` (amber, needs a human).
 * The distinction must read at a glance. `compact` is the footer-row form.
 */
const LEVELS: Record<
  AuthLevel,
  { text: string; surface: string; dot: string; glow: string; tag: string }
> = {
  auto: {
    text: 'text-auth-auto',
    surface: 'bg-auth-auto-bg border-auth-auto-border',
    dot: 'bg-auth-auto',
    glow: 'hover:shadow-glow-success',
    tag: '可直接执行',
  },
  confirm: {
    text: 'text-auth-confirm',
    surface: 'bg-auth-confirm-bg border-auth-confirm-border',
    dot: 'bg-auth-confirm',
    glow: 'hover:shadow-glow-confirm',
    tag: '需确认',
  },
};

interface AuthActionProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  level?: AuthLevel;
  children: ReactNode;
  hint?: string;
  icon?: ReactNode;
  compact?: boolean;
}

export function AuthAction({
  level = 'confirm',
  children,
  hint,
  icon,
  compact = false,
  disabled = false,
  className = '',
  ...rest
}: AuthActionProps) {
  const cfg = LEVELS[level];

  if (compact) {
    return (
      <button
        disabled={disabled}
        className={`inline-flex h-[38px] items-center justify-center gap-[7px] rounded-md border px-3 font-sans text-body font-semibold tracking-mono transition-shadow duration-fast ease-out ${
          cfg.surface
        } ${cfg.text} ${disabled ? 'cursor-not-allowed opacity-50' : `cursor-pointer ${cfg.glow}`} ${className}`}
        {...rest}
      >
        <span className={`h-[6px] w-[6px] flex-none rounded-full ${cfg.dot}`} />
        {children}
      </button>
    );
  }

  return (
    <button
      disabled={disabled}
      className={`flex w-full items-center gap-3 rounded-md border border-l-strong px-3 py-[10px] text-left font-sans transition-shadow duration-fast ease-out ${
        cfg.surface
      } ${cfg.text} border-l-current ${disabled ? 'cursor-not-allowed opacity-50' : `cursor-pointer ${cfg.glow}`} ${className}`}
      {...rest}
    >
      <span
        className={`grid h-[22px] w-[22px] flex-none place-items-center rounded-sm bg-surface-1 shadow-elev-1 ${cfg.text}`}
      >
        {icon ?? (level === 'auto' ? <Zap size={12} /> : <Check size={12} />)}
      </span>
      <span className="flex-1">
        <span className="block text-body font-semibold text-text-primary">{children}</span>
        <span className={`mt-[2px] block text-micro font-semibold ${cfg.text}`}>
          {hint ?? cfg.tag}
        </span>
      </span>
    </button>
  );
}
