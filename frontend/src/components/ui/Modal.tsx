import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

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
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className={`flex max-h-[88vh] w-full max-w-[92vw] flex-col overflow-hidden rounded-2xl border border-border-default bg-surface-1 shadow-popover ${widthClassName}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-none items-center justify-between gap-3 border-b border-border-default px-6 py-4">
          <div className="flex min-w-0 items-baseline gap-2">
            <span className="flex-none text-body font-semibold text-text-primary">{title}</span>
            {subtitle && (
              <span className="truncate text-caption font-normal text-text-tertiary">
                {subtitle}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="关闭"
            className="flex-none rounded-md p-1 text-text-tertiary transition-colors hover:bg-border-subtle hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </div>
        <div className={`min-h-0 flex-1 overflow-y-auto ${bodyClassName}`}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}
