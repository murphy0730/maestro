import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useExtensionOverlayHost } from './overlayHost';

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * ExtensionDrawer — 右侧 480px 抽屉。遮罩挂在 `<main>` 上，只盖内容区不盖会话栏。
 * Esc 关闭、Tab 焦点闭环、关闭后焦点回到触发元素。
 */
export function ExtensionDrawer({
  open,
  onClose,
  title,
  subtitle,
  header,
  footer,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  /** 标题行右侧的补充内容（状态徽章等）。 */
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const host = useExtensionOverlayHost();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => openerRef.current?.focus();
  }, [open]);

  if (!open || !host) return null;
  return createPortal(
    <>
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 z-20 bg-black/45 backdrop-blur-[5px]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 z-[21] flex w-[480px] max-w-[92%] flex-col border-l border-border-strong bg-surface-1 shadow-elev-3 outline-none"
      >
        <div className="flex flex-none items-start gap-[12px] border-b border-border-subtle px-[20px] pb-[14px] pt-[18px]">
          <div className="min-w-0 flex-1">
            <h2
              id={titleId}
              className="m-0 flex flex-wrap items-center gap-[8px] text-[15px] font-semibold text-text-primary"
            >
              {title}
              {header}
            </h2>
            {subtitle && (
              <div className="mt-[2px] truncate font-mono text-[11px] text-text-tertiary">
                {subtitle}
              </div>
            )}
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="grid h-[26px] w-[26px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors duration-fast hover:bg-surface-3 hover:text-text-primary"
          >
            <X size={14} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-[20px] py-[18px]">{children}</div>
        {footer && (
          <div className="flex flex-none items-center gap-[8px] border-t border-border-subtle bg-surface-1 px-[20px] py-[13px]">
            {footer}
          </div>
        )}
      </div>
    </>,
    host,
  );
}

/** 抽屉内的小节标题，等宽大写。 */
export function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-[20px]">
      <h3 className="hud-label mb-[8px] text-text-tertiary">{title}</h3>
      {children}
    </section>
  );
}

/** 键值表：左列说明、右列等宽真值。 */
export function DrawerKeyValues({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="m-0 grid grid-cols-[110px_1fr] gap-x-[14px] gap-y-[6px] text-[12px]">
      {rows.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-text-tertiary">{key}</dt>
          <dd className="m-0 break-all font-mono text-[11.5px] text-text-primary">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
