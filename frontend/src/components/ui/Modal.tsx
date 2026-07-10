import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

/**
 * Modal — a real dialog: `role="dialog"` + `aria-modal`, labelled by its own
 * title, Escape to close, focus moved in on open and returned to whatever
 * opened it on close. Left-aligned title; callers put the main action
 * bottom-right inside `children`.
 */
interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Muted note rendered next to the title (e.g. a constraint hint). */
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  /** Tailwind width class for the dialog shell. Defaults to a compact 420px. */
  widthClassName?: string;
  /** Tailwind padding for the scrollable body. Defaults to a compact p-4. */
  bodyClassName?: string;
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  widthClassName = 'w-[420px]',
  bodyClassName = 'p-4',
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Move focus into the dialog on open, hand it back to the opener on close.
  useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => openerRef.current?.focus();
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`flex max-h-[88vh] w-full max-w-[92vw] flex-col overflow-hidden rounded-lg border border-border-default bg-surface-1 shadow-popover outline-none ${widthClassName}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-none items-start justify-between gap-3 border-b border-border-subtle px-5 py-[14px]">
          <div className="flex min-w-0 flex-col gap-1">
            <span id={titleId} className="font-display text-h4 font-semibold text-text-primary">
              {title}
            </span>
            {subtitle && (
              <span className="text-caption font-normal leading-relaxed text-text-tertiary">
                {subtitle}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="关闭"
            className="grid h-[30px] w-[30px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors hover:bg-surface-2 hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>
        <div className={`min-h-0 flex-1 overflow-y-auto ${bodyClassName}`}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}
