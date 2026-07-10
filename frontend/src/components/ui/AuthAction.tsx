import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { AuthLevel } from '@/types';
import { BoltIcon, ShieldIcon } from '@/components/ui/Icon';

/**
 * Action button whose appearance encodes its authorization level.
 *
 * `auto` is solid green — 执行, safe to run without asking.
 * `confirm` keeps an amber outline: it is the one button in the app that
 * writes to MES on a human's authority, and it must not look like ordinary
 * execution. The bolt/shield icons carry the same distinction for anyone who
 * cannot separate the two hues.
 *
 * `compact` is the footer-row form.
 */
const LEVELS: Record<
  AuthLevel,
  { text: string; surface: string; hover: string; tag: string; Icon: typeof BoltIcon }
> = {
  auto: {
    text: 'text-on-solid',
    surface: 'bg-green-solid border-transparent',
    hover: 'hover:bg-green-solid-hover',
    tag: '可直接执行',
    Icon: BoltIcon,
  },
  confirm: {
    text: 'text-auth-confirm',
    surface: 'bg-auth-confirm-bg border-auth-confirm-border',
    hover: 'hover:bg-auth-confirm-bg',
    tag: '需确认',
    Icon: ShieldIcon,
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
  const { Icon } = cfg;

  if (compact) {
    return (
      <button
        disabled={disabled}
        className={`inline-flex h-control items-center justify-center gap-[6px] rounded-sm border px-3 font-sans text-body-sm font-medium transition-colors duration-fast ease-out ${
          cfg.surface
        } ${cfg.text} ${disabled ? 'cursor-not-allowed opacity-50' : `cursor-pointer ${cfg.hover}`} ${className}`}
        {...rest}
      >
        {icon ?? <Icon size={13} />}
        {children}
      </button>
    );
  }

  return (
    <button
      disabled={disabled}
      className={`flex w-full items-center gap-3 rounded-md border px-3 py-[10px] text-left font-sans transition-colors duration-fast ease-out ${
        cfg.surface
      } ${cfg.text} ${disabled ? 'cursor-not-allowed opacity-50' : `cursor-pointer ${cfg.hover}`} ${className}`}
      {...rest}
    >
      <span className="grid h-[22px] w-[22px] flex-none place-items-center">
        {icon ?? <Icon size={14} />}
      </span>
      <span className="flex-1">
        <span className="block text-body font-medium">{children}</span>
        <span className="mt-[2px] block text-micro font-medium opacity-80">{hint ?? cfg.tag}</span>
      </span>
    </button>
  );
}
