import { Check, X } from 'lucide-react';
import type { PendingActionPayload } from '@/types';
import { AuthAction } from '@/components/ui/AuthAction';

/**
 * PendingActionsCard — write actions held by the backend ActionGate, awaiting
 * human confirmation. Approve/reject is lifted to the parent (wired to
 * `POST /chat/confirm`); resolved actions render as a status line.
 */
interface PendingActionsCardProps {
  actions: PendingActionPayload[];
  onConfirm: (actionId: string, approved: boolean) => void;
}

const RESOLVED_LABEL: Record<Exclude<PendingActionPayload['status'], 'pending'>, string> = {
  executed: '✓ 已确认执行',
  rejected: '✕ 已取消',
  failed: '⚠ 执行失败',
};

export function PendingActionsCard({ actions, onConfirm }: PendingActionsCardProps) {
  return (
    <div className="mt-[11px] flex flex-col gap-2">
      {actions.map((a) => (
        <div
          key={a.action_id}
          className="rounded-md border border-auth-confirm-border bg-auth-confirm-bg px-3 py-[10px]"
        >
          <div className="flex items-center gap-2 text-caption font-semibold text-auth-confirm">
            <span className="h-[6px] w-[6px] flex-none rounded-full bg-auth-confirm" />
            待确认动作 · {a.action_type}
          </div>
          <p className="m-0 mt-1 text-body leading-relaxed text-text-primary">{a.description}</p>
          {a.status === 'pending' ? (
            <div className="mt-2 flex gap-2">
              <AuthAction
                compact
                level="confirm"
                icon={<Check size={14} />}
                onClick={() => onConfirm(a.action_id, true)}
              >
                确认执行
              </AuthAction>
              <button
                className="inline-flex h-[38px] cursor-pointer items-center gap-[6px] rounded-md border border-border-default bg-surface-3 px-3 font-sans text-body font-semibold text-text-secondary transition-shadow duration-fast ease-out hover:shadow-elev-1"
                onClick={() => onConfirm(a.action_id, false)}
              >
                <X size={14} />
                拒绝
              </button>
            </div>
          ) : (
            <div className="mt-2 text-caption font-semibold text-text-tertiary">
              {RESOLVED_LABEL[a.status]}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
