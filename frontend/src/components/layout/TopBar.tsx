import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { StatusDot, type DotTone } from '@/components/ui/StatusDot';
import type { RunMode } from '@/stores/uiPreferencesStore';
import type { TraceView } from '@/features/runtime/RunTrace';

export type ConnectionState = 'idle' | 'connecting' | 'streaming' | 'error' | 'uploading';

interface TopBarProps {
  session: string;
  mode: RunMode;
  connection: ConnectionState;
  clock: string;
  traceView: TraceView;
  hasRun: boolean;
  /** 真实的 run.status；没有运行时不渲染状态徽章。 */
  runStatus?: string;
  onTraceViewChange: (view: TraceView) => void;
}

const MODE_META: Record<RunMode, { label: string; tone: BadgeTone }> = {
  auto: { label: '自动', tone: 'accent' },
  planning: { label: '排产', tone: 'planning' },
  scheduling: { label: '调度', tone: 'scheduling' },
  query: { label: '查询', tone: 'query' },
};

const CONNECTION_META: Record<ConnectionState, { label: string; tone: DotTone; pulse: boolean }> = {
  idle: { label: '已连接', tone: 'success', pulse: false },
  connecting: { label: '正在连接', tone: 'accent', pulse: true },
  streaming: { label: '流式连接', tone: 'accent', pulse: true },
  uploading: { label: '正在上传', tone: 'accent', pulse: true },
  error: { label: '连接异常', tone: 'danger', pulse: false },
};

const RUN_STATUS_META: Record<string, { label: string; tone: BadgeTone }> = {
  created: { label: '已创建', tone: 'accent' },
  running_fast: { label: '快速执行', tone: 'accent' },
  structuring: { label: '结构化中', tone: 'controlled' },
  running_structured: { label: '受控执行', tone: 'controlled' },
  waiting_approval: { label: '待确认', tone: 'warning' },
  waiting_external: { label: '等待外部', tone: 'warning' },
  reconciling: { label: '对账中', tone: 'warning' },
  cancelling: { label: '正在取消', tone: 'neutral' },
  cancelled: { label: '已取消', tone: 'neutral' },
  failed: { label: '执行失败', tone: 'danger' },
  completed: { label: '已完成', tone: 'success' },
};

export function TopBar({ session, mode, connection, clock, traceView, hasRun, runStatus, onTraceViewChange }: TopBarProps) {
  const connectionMeta = CONNECTION_META[connection];
  const runMeta = runStatus ? RUN_STATUS_META[runStatus] : undefined;
  const traceHidden = traceView === 'hidden';
  return (
    <header className="flex h-header flex-none items-center gap-[12px] border-b border-border-subtle px-[18px]">
      <h1 className="cn-head m-0 max-w-[320px] truncate text-body-sm text-text-primary">{session || '新任务'}</h1>
      <Badge tone={MODE_META[mode].tone}>{MODE_META[mode].label}</Badge>
      {runMeta && <Badge tone={runMeta.tone}>{runMeta.label}</Badge>}
      <span className="flex-1" />
      <span role="status" className="flex items-center gap-[6px]">
        <StatusDot tone={connectionMeta.tone} pulse={connectionMeta.pulse} />
        <span className={`font-mono text-[10.5px] ${connection === 'error' ? 'text-status-error' : 'text-text-secondary'}`}>
          {connectionMeta.label}
        </span>
      </span>
      <span className="font-mono text-[11px] text-text-tertiary">{clock}</span>
      <button
        type="button"
        aria-label={traceHidden ? '显示运行详情' : '隐藏运行详情'}
        title={traceHidden ? '显示详情栏' : '详情栏'}
        disabled={!hasRun}
        onClick={() => onTraceViewChange(traceHidden ? 'docked' : 'hidden')}
        className="grid h-[26px] w-[26px] place-items-center rounded-md text-accent transition-colors duration-fast ease-out hover:bg-surface-3 disabled:text-text-disabled"
      >
        {traceHidden ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
      </button>
    </header>
  );
}
