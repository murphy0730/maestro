import {
  Check,
  CheckCircle2,
  Clock3,
  Bug,
  Expand,
  Minimize2,
  PanelRightClose,
  RefreshCw,
  ShieldAlert,
  X,
} from 'lucide-react';
import { Link, useInRouterContext } from 'react-router-dom';
import { API_BASE } from '@/api/client';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import type { ApprovalView, RunStep } from '@/types/api/runs';
import type { RunProjection } from '@/stores/runStore';
import {
  compactActivities,
  friendlyRuntimeText,
  presentActivity,
  presentRuntimeName,
  runStatusLabel,
  stepStatusLabel,
  type ActivityPresentation,
  type ActivityTone,
} from './runtimePresentation';

export type TraceView = 'docked' | 'hidden' | 'fullscreen';

interface RunTraceProps {
  projection: RunProjection;
  onApprove: (approval: ApprovalView, approved: boolean) => void;
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
const traceButton =
  'grid h-[26px] w-[26px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-accent';

/**
 * RunTrace — 设计稿 A/B/E 的运行详情栏：驻留 308px / 隐藏 / 全屏三态。
 * 只渲染 API 真实提供的字段（run id、revision、路径、步骤、审批、事件与诊断）。
 */
export function RunTrace({
  projection,
  onApprove,
  approvalError,
  view = 'docked',
  onViewChange = () => undefined,
}: RunTraceProps) {
  const inRouter = useInRouterContext();
  const run = projection.run;
  if (!run || view === 'hidden') return null;
  const fullscreen = view === 'fullscreen';
  const terminal =
    run.status in terminalLabels ? (run.status as keyof typeof terminalLabels) : undefined;
  // 已经确认过的那一张不再是「待审批」，哪怕快照还没回来。
  const pending =
    run.status === 'waiting_approval'
      ? run.pending_approvals.filter(
          (approval) =>
            approval.status === 'pending' &&
            approval.approval_id !== projection.resuming?.approvalId,
        )
      : [];

  const overview = <OverviewSection projection={projection} />;
  const steps = <StepsSection projection={projection} />;
  const approvals = (
    <ApprovalSection
      pending={pending}
      resuming={projection.resuming}
      approvalError={approvalError}
      onApprove={onApprove}
    />
  );
  const events = <EventsSection projection={projection} />;

  return (
    <aside
      aria-label="运行详情"
      className={`${fullscreen ? 'absolute inset-0 z-40 w-full bg-surface-1' : 'responsive-trace w-[308px] flex-none border-l bg-surface-1'} flex min-h-0 flex-col border-border-subtle`}
    >
      <header className="flex h-[50px] flex-none items-center gap-[8px] border-b border-border-subtle px-[16px]">
        <h2 className="hud-label m-0 text-text-tertiary">运行详情{fullscreen ? ' · 全屏' : ''}</h2>
        <span className="ml-auto flex items-center gap-[5px]">
          {terminal && <Badge tone={terminalTones[terminal]}>{terminalLabels[terminal]}</Badge>}
          {inRouter ? (
            <Link
              to={`/debug/runs/${encodeURIComponent(run.run_id)}`}
              aria-label="打开运行调试"
              title="运行调试"
              className={traceButton}
            >
              <Bug size={14} />
            </Link>
          ) : (
            <span aria-label="打开运行调试" className={traceButton}>
              <Bug size={14} />
            </span>
          )}
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
          {runStatusLabel(run.status)}
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
  const run = projection.run!;
  const steps = Object.values(run.steps);
  const done = steps.filter((step) => step.status === 'succeeded').length;
  const progress = steps.length === 0 ? 0 : Math.round((done / steps.length) * 100);
  const terminal = ['completed', 'failed', 'cancelled'].includes(run.status);
  return (
    <section className="border-b border-border-subtle px-[16px] py-[14px]">
      <div className="mb-[12px] flex items-center gap-[8px]">
        <h3 className="hud-label m-0 text-text-tertiary">执行步骤</h3>
        <span className="ml-auto font-mono text-[10px] text-text-tertiary">
          {steps.length > 0 ? `${done}/${steps.length} 已完成` : terminal ? '无需拆分' : '等待计划'}
        </span>
      </div>
      {steps.length > 0 && (
        <div
          className="mb-[14px] h-px overflow-hidden bg-border-subtle"
          role="progressbar"
          aria-label="执行步骤进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className="h-full bg-accent transition-[width] duration-slow ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      <ol className="step-timeline m-0 list-none p-0">
        {steps.map((step) => {
          const name = presentRuntimeName(step.kind);
          return (
            <li key={step.step_id}>
              <StepMarker status={step.status} />
              <div
                className={`text-body-sm font-medium leading-snug ${step.status === 'pending' ? 'text-text-tertiary' : 'text-text-primary'}`}
              >
                {name.label}
              </div>
              <div className="mt-[3px] flex flex-wrap items-center gap-x-[6px] font-mono text-[10.5px] text-text-tertiary">
                <span>{stepStatusLabel(step.status)}</span>
                {name.context && (
                  <>
                    <span aria-hidden="true" className="text-border-strong">
                      /
                    </span>
                    <span>{name.context}</span>
                  </>
                )}
              </div>
              {step.error_message && (
                <p className="mb-0 mt-[5px] text-caption leading-relaxed text-status-error">
                  {friendlyRuntimeText(step.error_message)}
                </p>
              )}
              {step.output_ref && (
                <a
                  href={`${API_BASE}/artifacts/${encodeURIComponent(step.output_ref)}`}
                  className="mt-[5px] block truncate font-mono text-[10px] text-accent hover:underline"
                >
                  查看任务产物
                </a>
              )}
            </li>
          );
        })}
        {steps.length === 0 && (
          <li className="pl-0 text-caption text-text-tertiary">
            {terminal ? '本次运行无需拆分步骤' : '正在准备执行步骤…'}
          </li>
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
  const showPathUpgrade = Boolean(projection.upgradeReason);
  const showWaiting = ['waiting_approval', 'reconciling', 'waiting_external'].includes(run.status);
  if (!showPathUpgrade && !showWaiting) return null;
  return (
    <div className="mt-[12px] space-y-[6px] text-body-sm">
      {showPathUpgrade && (
        <div className="flex items-center gap-[8px] text-text-secondary">
          <Check size={13} className="text-accent" />
          已升级为受控执行
        </div>
      )}
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
  resuming,
  approvalError,
  onApprove,
}: {
  pending: ApprovalView[];
  resuming?: RunProjection['resuming'];
  approvalError?: string;
  onApprove: RunTraceProps['onApprove'];
}) {
  if (pending.length === 0 && !resuming && !approvalError) return null;
  return (
    <section className="border-b border-border-subtle px-[16px] py-[14px]">
      <h3 className="hud-label mb-[10px] text-text-tertiary">
        {pending.length === 0 && resuming ? '已确认' : '待审批'}
      </h3>
      {resuming && (
        <div className="approval-card hud-brackets mb-[8px] flex items-center gap-[8px] rounded-lg p-[16px] text-body-sm text-text-secondary">
          <StatusDot tone={resuming.approved ? 'accent' : 'danger'} pulse />
          {resuming.approved ? '已确认 · 正在执行…' : '已拒绝 · 正在收尾…'}
        </div>
      )}
      {pending.map((approval) => {
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
                onClick={() => onApprove(approval, true)}
                className="confirm-key rounded-sm px-[12px] py-[5px] text-[11.5px] font-medium transition duration-fast"
              >
                确认
              </button>
              <button
                type="button"
                onClick={() => onApprove(approval, false)}
                className="rounded-sm border border-border-strong px-[12px] py-[5px] text-[11.5px] text-text-primary transition-colors duration-fast hover:border-status-error hover:text-status-error"
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
  const presented = projection.events.map(presentActivity);
  const activities = compactActivities(presented.filter((event) => !event.technical));
  const technical = compactActivities(presented.filter((event) => event.technical));
  const activityCount = activities.reduce((total, event) => total + event.count, 0);
  const technicalCount = technical.reduce((total, event) => total + event.count, 0);
  return (
    <section className="px-[16px] py-[14px]">
      <div className="mb-[12px] flex items-center gap-[8px]">
        <h3 className="hud-label m-0 text-text-tertiary">活动记录</h3>
        {activityCount > 0 && (
          <span className="ml-auto font-mono text-[10px] text-text-tertiary">
            {activityCount} 条
          </span>
        )}
      </div>
      {projection.upgradeReason && (
        <p className="controlled-path mb-[12px] rounded-r-md border-l-2 border-path-controlled px-[9px] py-[7px] text-caption leading-relaxed">
          已切换为受控执行 · {friendlyRuntimeText(projection.upgradeReason)}
        </p>
      )}
      {activities.length > 0 && (
        <ol className="m-0 list-none space-y-[1px] p-0">
          {activities.map((activity, index) => (
            <ActivityRow activity={activity} key={`${activity.raw}-${index}`} />
          ))}
        </ol>
      )}
      {activities.length === 0 && projection.events.length > 0 && (
        <p className="m-0 text-caption text-text-tertiary">运行正在准备中…</p>
      )}
      {technical.length > 0 && (
        <details className="group mt-[12px] border-t border-border-subtle pt-[10px]">
          <summary className="cursor-pointer select-none text-caption text-text-tertiary transition-colors hover:text-text-secondary">
            技术事件 · {technicalCount}
          </summary>
          <ol className="mb-0 mt-[8px] list-none space-y-[6px] p-0">
            {technical.map((activity, index) => (
              <li
                key={`${activity.raw}-${index}`}
                className="flex items-center gap-[7px] text-caption text-text-tertiary"
              >
                <span className="h-[5px] w-[5px] flex-none rounded-full bg-border-strong" />
                <span>{activity.label}</span>
                {activity.count > 1 && <span className="font-mono">×{activity.count}</span>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {projection.diagnostics.length > 0 && (
        <ul className="mb-0 mt-[12px] list-none space-y-[6px] border-t border-border-subtle p-0 pt-[10px] text-caption">
          {projection.diagnostics.map((diagnostic, index) => (
            <li className="flex gap-[7px] text-status-warning" key={`${diagnostic}-${index}`}>
              <span aria-hidden="true">!</span>
              <span>{friendlyRuntimeText(diagnostic)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const activityToneClasses: Record<ActivityTone, string> = {
  neutral: 'border-border-strong bg-surface-1',
  active: 'dot-pulse border-accent bg-accent',
  success: 'border-status-success bg-status-success',
  warning: 'border-status-warning bg-status-warning',
  danger: 'border-status-error bg-status-error',
};

function ActivityRow({ activity }: { activity: ActivityPresentation }) {
  return (
    <li className="relative min-h-[45px] border-l border-border-subtle py-[7px] pl-[18px] last:border-l-transparent">
      <span
        aria-hidden="true"
        className={`absolute -left-[4px] top-[13px] h-[7px] w-[7px] rounded-full border ${activityToneClasses[activity.tone]}`}
      />
      <div className="flex min-w-0 items-baseline gap-[6px]">
        <span className="truncate text-body-sm font-medium text-text-primary">
          {activity.label}
        </span>
        {activity.count > 1 && (
          <span className="flex-none font-mono text-[10px] text-text-tertiary">
            ×{activity.count}
          </span>
        )}
      </div>
      {activity.detail && (
        <p className="m-0 mt-[2px] truncate text-caption text-text-tertiary">{activity.detail}</p>
      )}
    </li>
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
