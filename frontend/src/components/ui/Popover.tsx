import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';

/**
 * Popover — floating menu container with the macOS popover material
 * (translucent fill + backdrop blur). Position it from the caller via
 * `className` (e.g. `absolute right-0 top-[34px] w-[168px]`); the owner keeps
 * its own open state and click-outside handling.
 */
export function Popover({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`material-popover z-50 overflow-hidden rounded-lg border border-border-default py-1 shadow-popover ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

/** Uppercase eyebrow label for a popover section. */
export function PopoverLabel({ children }: { children: ReactNode }) {
  return (
    <span className="block px-3 pb-1 pt-1.5 text-micro font-semibold uppercase text-text-tertiary">
      {children}
    </span>
  );
}

interface PopoverItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Leading icon (lucide element). Inherits row color; muted on default tone. */
  icon?: ReactNode;
  /** Right-aligned element, e.g. a check mark on the selected item. */
  trailing?: ReactNode;
  tone?: 'default' | 'danger';
}

/** One row inside a Popover. */
export function PopoverItem({
  icon,
  trailing,
  tone = 'default',
  className = '',
  children,
  ...rest
}: PopoverItemProps) {
  const toneCls =
    tone === 'danger'
      ? 'text-status-error hover:bg-status-error-bg'
      : 'text-text-secondary hover:bg-border-subtle hover:text-text-primary';
  return (
    <button
      className={`flex w-full items-center gap-2 px-3 py-[7px] text-left text-body-sm transition-colors duration-fast ease-out ${toneCls} ${className}`}
      {...rest}
    >
      {icon && (
        <span className={`flex-none ${tone === 'default' ? 'text-text-tertiary' : ''}`}>
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {trailing}
    </button>
  );
}
