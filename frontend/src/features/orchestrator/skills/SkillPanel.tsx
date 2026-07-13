import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { EngineStrip, PanelFootNote } from '@/components/ui/panel';
import { ObservationTrace } from '@/features/scheduling/ObservationTrace';
import type { SkillContextData } from '@/stores/conversationStore';

const STOP_REASON_LABELS: Record<string, string> = {
  final: '执行完成',
  pending_confirmation: '等待动作确认',
  max_steps: '达到步数上限',
  stuck: '循环终止（疑似绕圈）',
  error: '执行出错',
};

interface SkillPanelProps {
  onClose?: () => void;
  context: SkillContextData;
}

/** Context panel for a skill run: real trace + skill names, no engine mock data. */
export function SkillPanel({ onClose, context }: SkillPanelProps) {
  const title = context.skillNames.join('、') || '技能执行';
  const stopLabel = context.stopReason
    ? (STOP_REASON_LABELS[context.stopReason] ?? context.stopReason)
    : null;
  return (
    <ContextPanel
      eyebrow="技能 · SKILL"
      title={title}
      badge={
        <Badge tone="accent" dot glow>
          技能
        </Badge>
      }
      onClose={onClose}
    >
      <EngineStrip route="skill" title={title} meta={`${context.steps.length} 步执行轨迹`} />

      <ObservationTrace steps={context.steps} />

      {stopLabel && <PanelFootNote>执行状态 · {stopLabel}</PanelFootNote>}
    </ContextPanel>
  );
}
