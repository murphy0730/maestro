import type { ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * Primary control.
 *
 * Colour carries meaning, not emphasis:
 *   primary (blue)   — 沟通与导航: send, new conversation, save settings
 *   execute (green)  — 执行: anything that actually changes the shop floor
 *   danger  (red)    — destructive
 * `accent` is the tinted low-emphasis blue; secondary/ghost are neutral.
 * Pure presentational.
 */
type Variant = 'primary' | 'execute' | 'accent' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-blue-solid text-on-solid border-transparent shadow-elev-1 hover:bg-blue-solid-hover',
  execute:
    'bg-green-solid text-on-solid border-transparent shadow-elev-1 hover:bg-green-solid-hover',
  accent: 'bg-accent-bg text-accent-fg border-accent-border',
  secondary: 'bg-surface-2 text-text-primary border-border-default hover:bg-surface-3',
  ghost: 'bg-transparent text-text-secondary border-transparent hover:bg-surface-2',
  danger: 'bg-status-error-bg text-status-error border-status-error/40',
};

const SIZES: Record<Size, string> = {
  sm: 'h-[26px] px-[9px] text-body-sm gap-[6px]',
  md: 'h-control px-3 text-body-sm gap-[6px]',
  lg: 'h-[38px] px-4 text-body gap-2',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children?: ReactNode;
  variant?: Variant;
  size?: Size;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  fullWidth?: boolean;
}

export function Button({
  children,
  variant = 'secondary',
  size = 'md',
  leadingIcon,
  trailingIcon,
  fullWidth = false,
  disabled = false,
  className = '',
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm border font-sans font-medium leading-none transition-colors duration-fast ease-out ${
        SIZES[size]
      } ${VARIANTS[variant]} ${fullWidth ? 'w-full' : 'w-auto'} ${
        disabled ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'
      } ${className}`}
      {...rest}
    >
      {leadingIcon}
      {children}
      {trailingIcon}
    </button>
  );
}
