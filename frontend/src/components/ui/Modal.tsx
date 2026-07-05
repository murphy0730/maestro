import { useEffect } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Tailwind width class for the dialog shell. Defaults to a compact 420px. */
  widthClassName?: string;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  widthClassName = 'w-[420px]',
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
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className={`${widthClassName} max-w-[90vw] rounded-xl border border-border-default bg-surface-1 shadow-popover`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <span className="text-body-sm font-semibold">{title}</span>
          <button
            onClick={onClose}
            aria-label="关闭"
            className="text-text-tertiary hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
