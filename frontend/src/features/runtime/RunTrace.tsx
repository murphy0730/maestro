import { CheckCircle2, Circle, RefreshCw, ShieldAlert, XCircle } from 'lucide-react';
import type { ApprovalView } from '@/types/api/runs';
import type { RunProjection } from '@/stores/runStore';

interface RunTraceProps { projection: RunProjection; onApprove: (approval: ApprovalView, approved: boolean) => void; approvingId?: string | null }
const labels = { completed: '已完成', failed: '执行失败', cancelled: '已取消' } as const;
export function RunTrace({ projection, onApprove, approvingId }: RunTraceProps) {
  const run = projection.run;
  if (!run) return null;
  const isTerminal = run.status in labels;
  return <aside aria-label="运行轨迹" className="w-[300px] flex-none border-l border-border-subtle bg-surface-1 px-4 py-5">
    <div className="flex items-center justify-between"><h2 className="m-0 text-body-sm font-semibold text-text-primary">Run Trace</h2><span className="font-mono text-micro text-text-tertiary">{run.run_id.slice(0, 8)}</span></div>
    <div className="mt-5 space-y-3 text-body-sm">
      <div className="flex items-center gap-2 text-text-secondary"><Circle size={14} className="text-accent" />{run.path === 'fast' ? '快速执行' : run.path === 'structured' ? '已升级为受控执行' : '准备执行'}</div>
      {run.status === 'waiting_approval' && <div className="flex items-center gap-2 text-auth-confirm"><ShieldAlert size={14} />等待确认</div>}
      {run.status === 'reconciling' && <div className="flex items-center gap-2 text-status-warning"><RefreshCw size={14} />正在对账</div>}
      {run.status === 'waiting_external' && <div className="flex items-center gap-2 text-text-secondary"><RefreshCw size={14} />已恢复</div>}
      {Object.values(run.steps).map((step) => <div key={step.step_id} className="flex items-center gap-2 text-text-secondary"><CheckCircle2 size={14} className={step.status === 'failed' ? 'text-status-error' : step.status === 'succeeded' ? 'text-status-success' : 'text-text-tertiary'} />{step.kind}</div>)}
      {isTerminal && <div className={`flex items-center gap-2 ${run.status === 'completed' ? 'text-status-success' : 'text-status-error'}`}><XCircle size={14} />{labels[run.status as keyof typeof labels]}</div>}
    </div>
    {run.pending_approvals.filter((approval) => approval.status === 'pending').map((approval) => <section key={approval.approval_id} className="mt-5 border-t border-border-subtle pt-4"><p className="m-0 text-body-sm text-text-primary">{approval.impact_summary || approval.policy_reason}</p><div className="mt-3 flex gap-2"><button type="button" disabled={approvingId === approval.approval_id} onClick={() => onApprove(approval, true)} className="h-control rounded-sm bg-auth-confirm px-3 text-caption font-medium text-white disabled:opacity-50">确认</button><button type="button" disabled={approvingId === approval.approval_id} onClick={() => onApprove(approval, false)} className="h-control rounded-sm border border-border-default px-3 text-caption text-text-secondary disabled:opacity-50">拒绝</button></div></section>)}
  </aside>;
}
