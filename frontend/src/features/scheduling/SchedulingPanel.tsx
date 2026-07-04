import { Send, ShieldCheck } from 'lucide-react';
import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { AuthAction } from '@/components/ui/AuthAction';
import { EngineStrip, SectionLabel, PanelFootNote } from '@/components/ui/panel';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { STATUS_CLASSES } from '@/lib/status';
import { SCHEDULING_PANEL, KIT_STATUS, type KitItem, type TaskOrder } from '@/mocks/panels';

function KitRow({ name, sub, have, need, status }: KitItem) {
  const s = KIT_STATUS[status];
  const cls = STATUS_CLASSES[s.tone];
  const pct = Math.round((have / need) * 100);
  return (
    <div className="flex items-center gap-[11px] border-b border-border-subtle py-[9px]">
      <span
        className={`h-2 w-2 flex-none rounded-full ${cls.dot} ${status === 'missing' ? '' : 'shadow-glow-success'}`}
      />
      <div className="min-w-0 flex-1">
        <div className="text-body-sm font-medium text-text-primary">{name}</div>
        <div className="mt-[1px] font-mono text-[10.5px] text-text-tertiary">{sub}</div>
      </div>
      <div className="w-16 flex-none">
        <ProgressBar percent={pct} fillClassName={cls.dot} />
        <div className={`mt-[3px] text-right font-mono text-[10px] font-semibold ${cls.text}`}>
          {have}/{need}
        </div>
      </div>
      <Badge tone={s.tone} size="sm">
        {s.label}
      </Badge>
    </div>
  );
}

function TaskOrderRow({ id, desc, level }: TaskOrder) {
  const auto = level === 'auto';
  const tint = auto ? 'border-l-auth-auto' : 'border-l-auth-confirm';
  const text = auto ? 'text-auth-auto' : 'text-auth-confirm';
  const surface = auto
    ? 'bg-auth-auto-bg border-auth-auto-border'
    : 'bg-auth-confirm-bg border-auth-confirm-border';
  const dot = auto ? 'bg-auth-auto' : 'bg-auth-confirm';
  return (
    <div
      className={`mb-2 flex items-center gap-[11px] rounded-md border border-l-[3px] border-border-default bg-surface-2 px-3 py-[11px] ${tint}`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-mono-sm font-semibold text-text-primary">{id}</span>
          <span
            className={`inline-flex h-[18px] items-center gap-1 rounded-pill border px-[7px] font-mono text-[9.5px] font-bold ${surface} ${text}`}
          >
            <span className={`h-[5px] w-[5px] rounded-full ${dot}`} />
            {auto ? 'AUTO' : 'CONFIRM'}
          </span>
        </div>
        <div className="mt-1 text-caption leading-snug text-text-secondary">{desc}</div>
        <div className={`mt-1 text-micro font-semibold ${text}`}>
          {auto ? '可直接执行' : '需确认 · 写入排程'}
        </div>
      </div>
      <button
        className={`inline-flex h-8 flex-none cursor-pointer items-center gap-[6px] rounded-md border px-3 font-sans text-caption font-semibold ${surface} ${text}`}
      >
        {auto ? <Send size={13} /> : <ShieldCheck size={13} />}
        {auto ? '下发' : '确认下发'}
      </button>
    </div>
  );
}

interface PanelProps {
  onClose?: () => void;
}

export function SchedulingPanel({ onClose }: PanelProps) {
  const d = SCHEDULING_PANEL;
  return (
    <ContextPanel
      eyebrow={d.eyebrow}
      title={d.title}
      badge={
        <Badge tone="scheduling" dot glow>
          调度
        </Badge>
      }
      onClose={onClose}
      footer={
        <>
          <div className="flex gap-[10px]">
            <AuthAction level="auto" compact className="flex-1">
              批量下发 AUTO（2）
            </AuthAction>
            <AuthAction level="confirm" compact className="flex-1">
              确认下发 CONFIRM（2）
            </AuthAction>
          </div>
          <PanelFootNote>AUTO 可直接执行；CONFIRM 写入排程前需逐条确认。</PanelFootNote>
        </>
      }
    >
      <EngineStrip route="scheduling" title={d.strip.title} meta={d.strip.meta} />

      <div>
        <SectionLabel
          right={
            <Badge tone="warning" dot size="sm">
              综合 92%
            </Badge>
          }
        >
          齐套检查清单
        </SectionLabel>
        {d.kit.map((k) => (
          <KitRow key={k.name} {...k} />
        ))}
      </div>

      <div>
        <SectionLabel
          right={<span className="font-mono text-[10.5px] text-text-tertiary">2 级授权</span>}
        >
          待下发任务令
        </SectionLabel>
        {d.orders.map((o) => (
          <TaskOrderRow key={o.id} {...o} />
        ))}
      </div>
    </ContextPanel>
  );
}
