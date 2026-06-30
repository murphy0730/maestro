import type { ReactNode } from 'react';
import { X } from 'lucide-react';

/**
 * ContextPanel — the right-hand dynamic context container. Header (eyebrow +
 * title + badge + close), scrollable body, sticky footer for actions. Engine
 * panels compose their content as children. Pure presentational shell.
 */
interface ContextPanelProps {
  title: string;
  eyebrow?: string;
  badge?: ReactNode;
  footer?: ReactNode;
  onClose?: () => void;
  children: ReactNode;
}

export function ContextPanel({ title, eyebrow, badge, footer, onClose, children }: ContextPanelProps) {
  return (
    <aside className="flex h-full w-full flex-col bg-surface-1 font-sans text-text-primary">
      <header className="flex flex-none items-start gap-[10px] border-b border-border-subtle px-4 py-[14px]">
        <div className="flex-1">
          {eyebrow && (
            <div className="mb-1 text-micro font-semibold uppercase tracking-eyebrow text-text-tertiary">{eyebrow}</div>
          )}
          <div className="flex items-center gap-2">
            <h2 className="m-0 text-h4 font-semibold tracking-mono">{title}</h2>
            {badge}
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-[26px] w-[26px] flex-none cursor-pointer place-items-center rounded-sm border border-border-default text-text-tertiary"
          >
            <X size={14} />
          </button>
        )}
      </header>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">{children}</div>
      {footer && (
        <footer className="flex flex-none flex-col gap-2 border-t border-border-subtle bg-bg-base p-[14px]">{footer}</footer>
      )}
    </aside>
  );
}
