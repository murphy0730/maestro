import { lazy, Suspense } from 'react';
import { PanelRight } from 'lucide-react';
import type { ActiveEngine, SchedulingTraceStep } from '@/types';
import { PlanningPanel } from '@/features/planning/PlanningPanel';
import { SchedulingPanel } from '@/features/scheduling/SchedulingPanel';

const KnowledgeManager = lazy(async () => ({
  default: (await import('@/features/query/KnowledgeManager')).KnowledgeManager,
}));

/**
 * ContextPanelHost — the shell that swaps the right panel's content to match
 * the active engine. Idle (null) shows the empty state. Controlled by props.
 */
function EmptyPanel() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-[14px] px-7 text-center">
      <span className="grid h-[46px] w-[46px] place-items-center rounded-md border border-border-default bg-surface-2 text-text-tertiary">
        <PanelRight size={20} />
      </span>
      <div className="max-w-[240px] text-body-sm leading-relaxed text-text-tertiary">
        上下文面板将在 Agent 路由到某个引擎并提出可执行方案时展开。
      </div>
    </div>
  );
}

interface ContextPanelHostProps {
  engine: ActiveEngine;
  onClose?: () => void;
  schedulingSteps?: SchedulingTraceStep[];
}

export function ContextPanelHost({ engine, onClose, schedulingSteps }: ContextPanelHostProps) {
  switch (engine) {
    case 'planning':
      return <PlanningPanel onClose={onClose} />;
    case 'scheduling':
      return <SchedulingPanel onClose={onClose} steps={schedulingSteps} />;
    case 'query':
      return (
        <Suspense fallback={<EmptyPanel />}>
          <KnowledgeManager onClose={onClose} />
        </Suspense>
      );
    default:
      return <EmptyPanel />;
  }
}
