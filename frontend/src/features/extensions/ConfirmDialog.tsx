import type { ReactNode } from 'react';
import { TriangleAlert } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';

/**
 * 危险操作的显式二次确认。确认键写清动作本身（「卸载技能」「删除连接器」），
 * 不写「确定」——按钮文案就是这次操作的唯一说明。
 */
export function ConfirmDialog({
  open,
  title,
  confirmLabel,
  busy,
  error,
  children,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  confirmLabel: string;
  busy?: boolean;
  error?: string;
  children: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onCancel}
      chrome={false}
      title={title}
      widthClassName="max-w-[400px]"
      bodyClassName="p-[20px]"
    >
      <h2 className="m-0 flex items-center gap-[9px] text-[14px] font-semibold text-text-primary">
        <TriangleAlert size={16} className="flex-none text-status-error" />
        {title}
      </h2>
      <div className="my-[10px] text-[12.5px] leading-[1.7] text-text-secondary">{children}</div>
      {error && (
        <p role="alert" className="mb-[10px] text-[11.5px] text-status-error">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-[8px]">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-sm border border-border-strong px-[14px] py-[7px] text-[12px] text-text-secondary transition-colors duration-fast hover:text-text-primary disabled:opacity-40"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="rounded-sm border border-status-error/45 px-[14px] py-[7px] text-[12px] font-medium text-status-error transition-colors duration-fast hover:bg-status-error-bg disabled:opacity-40"
        >
          {busy ? '处理中…' : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
