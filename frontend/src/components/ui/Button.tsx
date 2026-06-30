import type { ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * Primary control. Tech feel via thin border + subtle glow on primary;
 * ghost is borderless for dense toolbars. Pure presentational.
 */
type Variant = 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-text-on-color border-accent-strong shadow-glow-accent-sm',
  accent: 'bg-accent-bg text-accent-fg border-accent-border',
  secondary: 'bg-surface-2 text-text-primary border-border-default shadow-inset-top-hi',
  ghost: 'bg-transparent text-text-secondary border-transparent',
  danger: 'bg-status-error-bg text-status-error border-status-error/40',
};

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2 text-body-sm gap-[6px]',
  md: 'h-[34px] px-3 text-body gap-[7px]',
  lg: 'h-[42px] px-4 text-body-lg gap-2',
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
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-md border font-sans font-semibold leading-none tracking-mono transition-colors duration-fast ease-out ${
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
