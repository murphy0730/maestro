import {
  Check,
  CheckCircle2,
  Clock3,
  Expand,
  Minimize2,
  PanelRightClose,
  RefreshCw,
  ShieldAlert,
  X,
} from 'lucide-react';
import { API_BASE } from '@/api/client';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { ApprovalView, RunStep } from '@/types/api/runs';
import type { RunProjection } from '@/stores/runStore';

export type TraceView = 'docked' | 'hidden' | 'fullscreen';

interface RunTraceProps {
  projection: RunProjection;
  onApprove: (approval: ApprovalView, approved: boolean) => void;
  approvingId?: string | null;
  approvalError?: string;
  view?: TraceView;
  onViewChange?: (view: TraceView) => void;
}

const terminalLabels = { completed: '已完成', failed: '执行失败', cancelled: '已取消' } as const;
const terminalTones: Record<keyof typeof terminalLabels, BadgeTone> = {
  completed: 'success',
  failed: 'danger',
  cancelled: 'neutral',
};
const stepLabels: Record<RunStep['status'], string> = {
  pending: '等待',
  ready: '就绪',
  waiting_approval: '待审批',
  running: '运行中',
  waiting_external: '等待外部',
  reconciling: '对账中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  skipped: '已跳过',
};

const traceButton =
  'grid h-[26px] w-[26px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-accent';

/**
 * RunTrace — 设计稿 A/B/E 的运行详情栏：驻留 308px / 隐藏 / 全屏三态。
 * 只渲染 API 真实提供的字段（run id、revision、路径、步骤、审批、事件与诊断）。
 */
export function RunTrace({
  projection,
  onApprove,
  approvingId,
  approvalError,
  view = 'docked',
  onViewChange = () => undefined,
}: RunTraceProps) {
  const run = projection.run;
  if (!run || view === 'hidden') return null;
  const fullscreen = view === 'fullscreen';
  const terminal =
    run.status in terminalLabels ? (run.status as keyof typeof terminalLabels) : undefined;
  const pending = run.pending_approvals.filter((approval) => approval.status === 'pending');

  const overview = <OverviewSection projection={projection} />;
  const steps = <StepsSection projection={projection} />;
  const approvals = (
    <ApprovalSection
      pending={pending}
      approvingId={approvingId}
      approvalError={approvalError}
      onApprove={onApprove}
    />
  );
  const events = <EventsSection projection={projection} />;

  return (
    <aside
      aria-label="运行轨迹"
      className={`${fullscreen ? 'absolute inset-0 z-40 w-full bg-surface-1' : 'responsive-trace w-[308px] flex-none border-l bg-surface-1'} flex min-h-0 flex-col border-border-subtle`}
    >
      <header className="flex h-[50px] flex-none items-center gap-[8px] border-b border-border-subtle px-[16px]">
        <h2 className="hud-label m-0 text-text-tertiary">运行轨迹{fullscreen ? ' · 全屏' : ''}</h2>
        <span className="ml-auto flex items-center gap-[5px]">
          {terminal && <Badge tone={terminalTones[terminal]}>{terminalLabels[terminal]}</Badge>}
          {fullscreen ? (
            <button
              type="button"
              aria-label="还原驻留详情"
              title="还原驻留"
              onClick={() => onViewChange('docked')}
              className={traceButton}
            >
              <Minimize2 size={14} />
            </button>
          ) : (
            <button
              type="button"
              aria-label="全屏运行详情"
              title="全屏"
              onClick={() => onViewChange('fullscreen')}
              className={traceButton}
            >
              <Expand size={14} />
            </button>
          )}
          <button
            type="button"
            aria-label="隐藏运行详情"
            title={fullscreen ? '关闭' : '隐藏'}
            onClick={() => onViewChange('hidden')}
            className={traceButton}
          >
            {fullscreen ? <X size={14} /> : <PanelRightClose size={14} />}
          </button>
        </span>
      </header>

      {fullscreen ? (
        <div className="grid min-h-0 flex-1 grid-cols-[1.1fr_.9fr] gap-[16px] overflow-y-auto p-[18px] max-lg:grid-cols-1 [&_section]:border-b-0 [&_section]:px-0">
          <div className="min-w-0">
            {overview}
            {steps}
            {events}
          </div>
          <div className="min-w-0">{approvals}</div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {overview}
          {steps}
          {approvals}
          {events}
        </div>
      )}
    </aside>
  );
}

function OverviewSection({ projection }: { projection: RunProjection }) {
  const run = projection.run!;
  const pathTone: BadgeTone =
    run.path === 'structured' ? 'controlled' : run.path === 'fast' ? 'accent' : 'neutral';
  const pathLabel =
    run.path === 'fast' ? '快速执行' : run.path === 'structured' ? '受控执行' : '路径选择中';
  return (
    <section className="border-b border-border-subtle px-[16px] py-[14px]">
      <div className="flex flex-wrap items-center gap-[8px]">
        <Badge tone={pathTone}>{`${pathLabel} · 第 ${run.revision} 版`}</Badge>
        {projection.recovered && (
          <Badge tone="success" icon={<CheckCircle2 size={11} />}>
            已恢复
          </Badge>
        )}
      </div>
      <dl className="mt-[12px] grid grid-cols-[52px_1fr] gap-y-[4px] text-caption">
        <dt className="text-text-tertiary">Run</dt>
        <dd className="m-0 truncate font-mono text-text-secondary" title={run.run_id}>
          {run.run_id}
        </dd>
        <dt className="text-text-tertiary">状态</dt>
        <dd className="m-0 flex items-center gap-[6px] text-text-primary">
          {run.status === 'waiting_approval' && (
            <ShieldAlert size={12} className="text-auth-confirm" />
          )}
          {(run.status === 'reconciling' || run.status === 'waiting_external') && (
            <RefreshCw size={12} className="text-status-warning" />
          )}
          {statusLabel(run.status)}
        </dd>
        {run.created_at && (
          <>
            <dt className="text-text-tertiary">开始</dt>
            <dd className="m-0 font-mono text-text-secondary">
              {new Date(run.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
            </dd>
          </>
        )}
      </dl>
    </section>
  );
}

function StepsSection({ projection }: { projection: RunProjection }) {
  const steps = Object.values(projection.run!.steps);
  const done = steps.filter((step) => step.status === 'succeeded').length;
  return (
    <section className="border-b border-border-subtle px-[16px] py-[14px]">
      <h3 className="hud-label mb-[10px] text-text-tertiary">
        步骤 · {done}/{steps.length}
      </h3>
      <ol className="step-timeline m-0 list-none p-0">
        {steps.map((step) => (
          <li key={step.step_id}>
            <StepMarker status={step.status} />
            <div
              className={`text-body-sm ${step.status === 'pending' ? 'text-text-tertiary' : 'text-text-primary'}`}
            >
              {step.kind}
            </div>
            <div className="font-mono text-[10.5px] text-text-tertiary">
              {stepLabels[step.status]}
              {step.error_message ? ` · ${step.error_message}` : ''}
            </div>
            {step.output_ref && (
              <a
                href={`${API_BASE}/artifacts/${encodeURIComponent(step.output_ref)}`}
                className="mt-[4px] block truncate font-mono text-[10px] text-accent hover:underline"
              >
                产物 {step.output_ref}
              </a>
            )}
          </li>
        ))}
        {steps.length === 0 && (
          <li className="pl-0 text-caption text-text-tertiary">等待运行步骤…</li>
        )}
      </ol>
      <RunStateLine projection={projection} />
    </section>
  );
}

/**
 * 关键状态的文字说明 —— 颜色不是唯一载体。终态与「已恢复」已经由概览徽章承载，
 * 这里只补充徽章说不清楚的执行路径与等待原因。
 */
function RunStateLine({ projection }: { projection: RunProjection }) {
  const run = projection.run!;
  return (
    <div className="mt-[12px] space-y-[6px] text-body-sm">
      <div className="flex items-center gap-[8px] text-text-secondary">
        <Check size={13} className="text-accent" />
        {run.path === 'fast'
          ? '快速执行'
          : run.path === 'structured'
            ? '已升级为受控执行'
            : '准备执行'}
      </div>
      {run.status === 'waiting_approval' && (
        <div className="flex items-center gap-[8px] text-auth-confirm">
          <ShieldAlert size={13} />
          等待确认
        </div>
      )}
      {run.status === 'reconciling' && (
        <div className="flex items-center gap-[8px] text-status-warning">
          <RefreshCw size={13} />
          正在对账
        </div>
      )}
      {run.status === 'waiting_external' && (
        <div className="flex items-center gap-[8px] text-text-secondary">
          <RefreshCw size={13} />
          等待外部完成
        </div>
      )}
    </div>
  );
}

function ApprovalSection({
  pending,
  approvingId,
  approvalError,
  onApprove,
}: {
  pending: ApprovalView[];
  approvingId?: string | null;
  approvalError?: string;
  onApprove: RunTraceProps['onApprove'];
}) {
  if (pending.length === 0 && !approvalError) return null;
  return (
    <section className="border-b border-border-subtle px-[16px] py-[14px]">
      <h3 className="hud-label mb-[10px] text-text-tertiary">待审批</h3>
      {pending.map((approval) => {
        const busy = approvingId === approval.approval_id;
        const required = approval.confirmations_required ?? 1;
        // 双重确认下第二轮长得和第一轮一样，不标出来会让人以为上次没点上。
        const round = required > 1 ? (approval.confirmations?.length ?? 0) + 1 : 0;
        return (
          <div
            key={approval.approval_id}
            className="approval-card hud-brackets mb-[8px] rounded-lg p-[16px]"
          >
            <div className="hud-label mb-[8px] flex items-center gap-[8px] text-auth-confirm">
              <ShieldAlert size={12} />
              操作审批 · 第 {approval.run_revision} 版
              {round > 0 && (
                <span className="ml-auto font-mono text-[10px]">
                  第 {round}/{required} 次确认
                </span>
              )}
            </div>
            <p className="mb-[4px] text-[13.5px] font-medium text-text-primary">
              {approval.impact_summary}
            </p>
            <p className="m-0 font-mono text-[11px] leading-relaxed text-text-tertiary">
              {approval.policy_reason}
            </p>
            {round > 1 && (
              <p className="mt-[6px] m-0 text-[11px] leading-relaxed text-text-tertiary">
                此操作要求多次确认；本次确认同时校验外部状态在两次之间未发生变化。
              </p>
            )}
            {approval.expires_at && (
              <p className="mt-[8px] flex items-center gap-[4px] font-mono text-[10.5px] text-text-tertiary">
                <Clock3 size={11} />
                {new Date(approval.expires_at).toLocaleTimeString('zh-CN', { hour12: false })}{' '}
                前有效
              </p>
            )}
            <div className="mt-[12px] flex gap-[8px]">
              <button
                type="button"
                aria-label="确认"
                aria-busy={busy}
                disabled={busy}
                onClick={() => onApprove(approval, true)}
                className="confirm-key rounded-sm px-[12px] py-[5px] text-[11.5px] font-medium transition duration-fast disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
              >
                {busy ? '提交中…' : '确认'}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onApprove(approval, false)}
                className="rounded-sm border border-border-strong px-[12px] py-[5px] text-[11.5px] text-text-primary transition-colors duration-fast hover:border-status-error hover:text-status-error disabled:cursor-not-allowed disabled:opacity-50"
              >
                拒绝
              </button>
            </div>
          </div>
        );
      })}
      {approvalError && (
        <p
          role="alert"
          className="rounded-md bg-status-error-bg p-[12px] text-caption text-status-error"
        >
          {approvalError}
        </p>
      )}
    </section>
  );
}

function EventsSection({ projection }: { projection: RunProjection }) {
  if (
    !projection.upgradeReason &&
    projection.events.length === 0 &&
    projection.diagnostics.length === 0
  )
    return null;
  return (
    <section className="px-[16px] py-[14px]">
      <h3 className="hud-label mb-[10px] text-text-tertiary">事件</h3>
      {projection.upgradeReason && (
        <p className="controlled-path mb-[8px] rounded-r-md border-l-2 border-path-controlled px-[8px] py-[6px] text-caption">
          路径升级：{projection.upgradeReason}
        </p>
      )}
      <ul className="m-0 list-none p-0 font-mono text-[10px] leading-[1.9] text-text-tertiary">
        {projection.events.map((event, index) => (
          <li key={`${event}-${index}`}>{event}</li>
        ))}
        {projection.diagnostics.map((diagnostic, index) => (
          <li className="text-status-warning" key={`${diagnostic}-${index}`}>
            诊断 · {diagnostic}
          </li>
        ))}
      </ul>
    </section>
  );
}

function statusLabel(status: string) {
  return (
    (
      {
        created: '已创建',
        running_fast: '快速运行中',
        structuring: '正在结构化',
        running_structured: '受控运行中',
        waiting_approval: '等待审批',
        waiting_external: '等待外部',
        reconciling: '对账中',
        cancelling: '正在取消',
        cancelled: '已取消',
        failed: '执行失败',
        completed: '已完成',
      } as Record<string, string>
    )[status] ?? status
  );
}

/** 设计稿 .steps .n：15px 状态圆点，落在时间线的竖线上。 */
function StepMarker({ status }: { status: RunStep['status'] }) {
  const base =
    'absolute left-0 top-[3px] grid h-[15px] w-[15px] place-items-center rounded-full border-[1.5px] text-[9px]';
  if (status === 'succeeded')
    return (
      <span
        aria-hidden="true"
        className={`${base} border-status-success bg-status-success text-on-success`}
      >
        <Check size={9} strokeWidth={3} />
      </span>
    );
  if (status === 'failed' || status === 'cancelled')
    return (
      <span aria-hidden="true" className={`${base} border-status-error text-status-error`}>
        <X size={9} strokeWidth={3} />
      </span>
    );
  if (status === 'running' || status === 'reconciling')
    return (
      <span
        aria-hidden="true"
        className={`${base} dot-pulse border-accent shadow-[0_0_0_3px_var(--accent-bg)]`}
      />
    );
  return <span aria-hidden="true" className={`${base} border-border-strong`} />;
}
