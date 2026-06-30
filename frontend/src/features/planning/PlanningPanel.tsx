import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { AuthAction } from '@/components/ui/AuthAction';
import { EngineStrip, SectionLabel, ParamRow, PanelFootNote } from '@/components/ui/panel';
import { PLANNING_PANEL } from '@/mocks/panels';

/** Capacity load bar — warns (amber) at >= 95% utilization. */
function CapacityBar({ name, used }: { name: string; used: number }) {
  const hot = used >= 95;
  return (
    <div className="mb-[11px]">
      <div className="mb-[5px] flex items-baseline gap-2">
        <span className="flex-1 text-body-sm text-text-secondary">{name}</span>
        <span className={`font-mono text-mono-sm font-semibold ${hot ? 'text-status-warning' : 'text-text-primary'}`}>
          {used}%
        </span>
      </div>
      <div className="h-[7px] overflow-hidden rounded-pill border border-border-subtle bg-surface-inset">
        <div
          className={`h-full rounded-pill bg-planning ${hot ? '' : 'shadow-glow-planning'}`}
          style={{ width: `${used}%` }}
        />
      </div>
    </div>
  );
}

interface PanelProps {
  onClose?: () => void;
}

export function PlanningPanel({ onClose }: PanelProps) {
  const d = PLANNING_PANEL;
  return (
    <ContextPanel
      eyebrow={d.eyebrow}
      title={d.title}
      badge={
        <Badge tone="planning" dot glow>
          排产
        </Badge>
      }
      onClose={onClose}
      footer={
        <>
          <div className="flex gap-[10px]">
            <AuthAction level="confirm" compact className="flex-1">
              提交排产方案
            </AuthAction>
            <AuthAction level="auto" compact className="flex-1">
              生成模拟预览
            </AuthAction>
          </div>
          <PanelFootNote>提交将写入 MES 排程，需主管确认后生效。</PanelFootNote>
        </>
      }
    >
      <EngineStrip route="planning" title={d.strip.title} meta={d.strip.meta} />

      <div>
        <SectionLabel right={<span className="font-mono text-[10.5px] text-accent-fg">1 项变更</span>}>参数确认</SectionLabel>
        {d.params.map((p) => (
          <ParamRow key={p.label} label={p.label} value={p.value} unit={p.unit} changed={p.changed} />
        ))}
      </div>

      <div>
        <SectionLabel
          right={
            <Badge tone="warning" dot size="sm">
              综合 96%
            </Badge>
          }
        >
          产能负载 · 工段
        </SectionLabel>
        {d.capacity.map((c) => (
          <CapacityBar key={c.name} name={c.name} used={c.used} />
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {d.badges.map((b) => (
          <Badge key={b.text} tone={b.tone} dot glow={b.glow}>
            {b.text}
          </Badge>
        ))}
      </div>
    </ContextPanel>
  );
}
