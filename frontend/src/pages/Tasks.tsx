import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ArrowLeft } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { AuthAction } from '@/components/ui/AuthAction';
import { GanttChart } from '@/features/planning/GanttChart';
import {
  TASKS_GANTT,
  TASKS_KPIS,
  TASKS_KPI_DELTA,
  TASKS_NOW,
  TASKS_RUN,
  WORK_ORDERS,
  type OrderStatus,
  type WorkOrder,
} from '@/mocks/tasks';

/**
 * Tasks — the summary-before-detail view of one planning run.
 *
 * Four compact KPIs answer "is this schedule any good"; the gantt answers
 * "where does time get stuck"; the table answers "which work order exactly".
 * Data is mocked (see `@/mocks/tasks`) — the backend has no `GET /tasks` yet.
 */

const FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'running', label: '进行中' },
  { id: 'pending', label: '待下发' },
  { id: 'blocked', label: '阻塞' },
] as const;
type FilterId = (typeof FILTERS)[number]['id'];

const STATUS_META: Record<OrderStatus, { tone: 'success' | 'warning' | 'error'; label: string }> = {
  running: { tone: 'success', label: '进行中' },
  pending: { tone: 'warning', label: '待确认' },
  auto: { tone: 'success', label: '可自动' },
  blocked: { tone: 'error', label: '缺料阻塞' },
};

const PRIORITY_META: Record<WorkOrder['priority'], { bar: string; label: string }> = {
  urgent: { bar: 'bg-status-error', label: '紧急' },
  high: { bar: 'bg-status-warning', label: '高' },
  normal: { bar: 'bg-text-disabled', label: '常规' },
};

/** `2026-07-02T18:30:00` → `07-02 18:30` */
function formatDue(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => n.toString().padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function Kpi({
  label,
  value,
  unit,
  delta,
  deltaTone = 'good',
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: string;
  deltaTone?: 'good' | 'bad' | 'flat';
}) {
  const tone =
    deltaTone === 'good'
      ? 'text-status-success'
      : deltaTone === 'bad'
        ? 'text-status-error'
        : 'text-text-tertiary';
  return (
    <div className="rounded-md border border-border-subtle bg-surface-1 px-[11px] py-[9px]">
      <div className="text-[10px] uppercase tracking-eyebrow text-text-tertiary">{label}</div>
      <div className="mt-px font-display text-[19px] font-semibold leading-tight tracking-tight text-text-primary">
        {value}
        {unit && <span className="text-caption font-medium text-text-tertiary">{unit}</span>}
      </div>
      <div className={`font-mono text-[10.5px] ${delta ? tone : 'text-text-tertiary'}`}>
        {delta ?? '—'}
      </div>
    </div>
  );
}

export function Tasks() {
  const [filter, setFilter] = useState<FilterId>('all');
  const [search, setSearch] = useState('');

  const orders = useMemo(() => {
    const q = search.trim().toLowerCase();
    return WORK_ORDERS.filter((o) => {
      if (filter !== 'all' && o.status !== filter) return false;
      if (!q) return true;
      return `${o.id} ${o.desc} ${o.stage}`.toLowerCase().includes(q);
    });
  }, [filter, search]);

  const blocked = WORK_ORDERS.filter((o) => o.status === 'blocked').length;
  const ganttDay = formatDue(TASKS_GANTT.tasks[0].start).slice(0, 5);

  return (
    <div className="flex h-full flex-col bg-bg-base">
      <header className="flex flex-none items-center gap-[10px] border-b border-border-subtle px-4 py-[10px]">
        <Link
          to="/"
          aria-label="返回工作区"
          title="返回工作区"
          className="grid h-[30px] w-[30px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors hover:bg-surface-2 hover:text-text-primary"
        >
          <ArrowLeft size={16} />
        </Link>
        <span className="font-display text-body-sm font-medium text-text-primary">
          {TASKS_RUN.line} · 排产运行 #{TASKS_RUN.id.replace('run-', '')}
        </span>
        <Badge tone="success" dot size="sm">
          {TASKS_RUN.status}
        </Badge>
        <span className="ml-auto flex items-center gap-2 font-mono text-caption text-text-tertiary">
          <span className="h-[6px] w-[6px] rounded-full bg-status-success ring-[3px] ring-status-success-bg" />
          MES 已连接
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mb-[14px] flex flex-wrap items-center gap-2">
          <label className="flex h-[30px] min-w-[220px] items-center gap-[7px] rounded-sm border border-border-default bg-surface-inset px-[10px]">
            <Search size={13} className="flex-none text-text-tertiary" aria-hidden="true" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索工单号、物料、工段"
              aria-label="搜索工单"
              className="w-full border-none bg-transparent text-body-sm text-text-primary outline-none placeholder:text-text-disabled"
            />
          </label>

          <div
            role="tablist"
            aria-label="按状态筛选"
            className="inline-flex gap-[2px] rounded-md border border-border-subtle bg-surface-inset p-[2px]"
          >
            {FILTERS.map((f) => (
              <button
                key={f.id}
                role="tab"
                aria-selected={filter === f.id}
                onClick={() => setFilter(f.id)}
                className={`inline-flex h-[26px] items-center rounded-sm px-[11px] text-caption font-medium transition-colors duration-fast ease-out ${
                  filter === f.id
                    ? 'bg-surface-3 text-text-primary shadow-elev-1'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <Button size="sm" variant="secondary" className="ml-auto">
            导出
          </Button>
          <Button size="sm" variant="primary">
            重新求解
          </Button>
        </div>

        {/* Summary before detail */}
        <div className="mb-[14px] grid grid-cols-2 gap-2 md:grid-cols-4">
          <Kpi
            label="交期达成"
            value={(TASKS_KPIS.due_rate * 100).toFixed(1)}
            unit="%"
            delta={`▲ ${TASKS_KPI_DELTA.due_rate.toFixed(1)}`}
          />
          <Kpi
            label="Makespan"
            value={TASKS_KPIS.makespan_hours.toFixed(1)}
            unit="h"
            delta={`▼ ${Math.abs(TASKS_KPI_DELTA.makespan_hours).toFixed(1)}h`}
          />
          <Kpi
            label="换型次数"
            value={String(TASKS_KPIS.changeover_count)}
            delta="— 持平"
            deltaTone="flat"
          />
          <Kpi
            label="阻塞工单"
            value={String(blocked)}
            delta={blocked ? '工装夹具缺 1' : undefined}
            deltaTone="bad"
          />
        </div>

        <div className="mb-[14px]">
          <GanttChart data={TASKS_GANTT} title={`资源甘特 · ${ganttDay}`} now={TASKS_NOW} />
        </div>

        {/* Detail */}
        <div className="overflow-x-auto rounded-lg border border-border-subtle bg-surface-1">
          <table className="w-full min-w-[800px] border-collapse text-body-sm">
            <thead>
              <tr>
                {['工单', '产品 / 描述', '优先级', '工段', '数量', '交期', '状态', '操作'].map(
                  (h) => (
                    <th
                      key={h}
                      className={`whitespace-nowrap border-b border-border-subtle bg-surface-2 px-[14px] py-[10px] text-micro font-medium uppercase text-text-tertiary ${
                        h === '数量' || h === '交期' ? 'text-right' : 'text-left'
                      }`}
                    >
                      {h === '操作' ? <span className="sr-only">{h}</span> : h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const st = STATUS_META[o.status];
                const pr = PRIORITY_META[o.priority];
                return (
                  <tr key={o.id} className="transition-colors hover:bg-surface-2">
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px] font-mono text-caption text-text-primary">
                      {o.id}
                    </td>
                    <td className="border-b border-border-subtle px-[14px] py-[10px] font-medium text-text-primary">
                      {o.desc}
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px] text-text-secondary">
                      <span className="inline-flex items-center gap-[6px] text-caption">
                        <i className={`h-[13px] w-[3px] flex-none rounded-full ${pr.bar}`} />
                        {pr.label}
                      </span>
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px] text-text-secondary">
                      {o.stage}
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px] text-right font-mono text-text-primary">
                      {o.qty ?? '—'}
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px] text-right font-mono text-text-primary">
                      {formatDue(o.due)}
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px]">
                      <Badge tone={st.tone} dot size="sm">
                        {st.label}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap border-b border-border-subtle px-[14px] py-[10px]">
                      {o.status === 'pending' && (
                        <AuthAction
                          compact
                          level="confirm"
                          className="h-[26px] px-[9px] text-caption"
                        >
                          确认下发
                        </AuthAction>
                      )}
                      {(o.status === 'auto' || o.status === 'running') && (
                        <AuthAction compact level="auto" className="h-[26px] px-[9px] text-caption">
                          下发
                        </AuthAction>
                      )}
                      {o.status === 'blocked' && (
                        <Button size="sm" variant="ghost">
                          催料
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {orders.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="px-[14px] py-10 text-center text-body-sm text-text-tertiary"
                  >
                    没有匹配的工单。换个筛选条件或搜索词试试。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
