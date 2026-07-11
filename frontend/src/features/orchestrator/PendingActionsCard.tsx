import { Check, Loader2, TriangleAlert, X } from 'lucide-react';
import type { PendingActionPayload } from '@/types';
import { AuthAction } from '@/components/ui/AuthAction';
import { ShieldIcon } from '@/components/ui/Icon';

/**
 * PendingActionsCard — write actions held by the backend ActionGate, awaiting
 * human confirmation. Approve/reject is lifted to the parent (wired to
 * `POST /chat/confirm`); resolved actions render as a status line.
 */
interface PendingActionsCardProps {
  actions: PendingActionPayload[];
  onConfirm: (actionId: string, approved: boolean) => void;
}

const RESOLVED_LABEL: Record<
  Exclude<PendingActionPayload['status'], 'pending' | 'executing'>,
  { Icon: typeof Check; label: string }
> = {
  executed: { Icon: Check, label: '已确认执行' },
  rejected: { Icon: X, label: '已取消' },
  failed: { Icon: TriangleAlert, label: '执行失败' },
};

export function PendingActionsCard({ actions, onConfirm }: PendingActionsCardProps) {
  return (
    <div className="mt-[11px] flex flex-col gap-2">
      {actions.map((a) => (
        <div
          key={a.action_id}
          className="rounded-md border border-l-[3px] border-auth-confirm-border border-l-auth-confirm bg-auth-confirm-bg px-3 py-[10px]"
        >
          {/* The 3px stripe + uppercase tag + shield carry the authorization
              level, so the button below need not encode it a fourth time.
              While executing, the eyebrow flips to a live "正在执行工具" state. */}
          <div className="flex items-center gap-2 text-micro font-medium uppercase tracking-eyebrow text-auth-confirm">
            {a.status === 'executing' ? (
              <>
                <Loader2 size={12} className="flex-none animate-spin" />
                正在执行工具 · {a.action_type}
              </>
            ) : (
              <>
                <ShieldIcon size={12} className="flex-none" />
                CONFIRM · {a.action_type}
              </>
            )}
          </div>
          <p className="m-0 mt-[6px] text-body leading-relaxed text-text-primary">
            {a.description}
          </p>
          {a.status === 'pending' ? (
            <div className="mt-2 flex gap-2">
              <AuthAction compact level="confirm" onClick={() => onConfirm(a.action_id, true)}>
                确认执行
              </AuthAction>
              <button
                className="inline-flex h-control cursor-pointer items-center gap-[6px] rounded-sm px-3 font-sans text-body-sm font-medium text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-2 hover:text-text-primary"
                onClick={() => onConfirm(a.action_id, false)}
              >
                <X size={14} />
                拒绝
              </button>
            </div>
          ) : a.status === 'executing' ? (
            <div className="mt-2 flex items-center gap-[6px] text-caption font-semibold text-auth-confirm">
              <Loader2 size={13} className="flex-none animate-spin" />
              正在执行工具…
            </div>
          ) : (
            (() => {
              const { Icon, label } = RESOLVED_LABEL[a.status];
              return (
                <div className="mt-2 flex items-center gap-[6px] text-caption font-semibold text-text-tertiary">
                  <Icon size={13} className="flex-none" />
                  {label}
                </div>
              );
            })()
          )}
        </div>
      ))}
    </div>
  );
}
