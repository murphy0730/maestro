import { Box, Plug, Sparkles, Terminal } from 'lucide-react';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { CapabilityFamily, CapabilityLabel } from './capabilityLabel';

/**
 * CapabilityIdentity —— 一次能力调用的身份行：图标 + 人读标题 + 来源 + 归属徽章。
 *
 * 步骤列表与审批卡片共用，好让「我正在批的」与「轨迹里跑过的」长得一样。
 * 风险不靠颜色单独表达：写操作会额外挂一枚带文字的徽章。
 */

const FAMILY_META: Record<CapabilityFamily, { label: string; tone: BadgeTone }> = {
  mcp: { label: 'MCP', tone: 'accent' },
  tool: { label: '工具', tone: 'neutral' },
  skill: { label: '技能', tone: 'controlled' },
  unknown: { label: '能力', tone: 'neutral' },
};

function FamilyIcon({ family }: { family: CapabilityFamily }) {
  const props = { size: 12, 'aria-hidden': true as const, className: 'flex-none' };
  if (family === 'mcp') return <Plug {...props} className="flex-none text-accent" />;
  if (family === 'skill') return <Sparkles {...props} className="flex-none text-path-controlled" />;
  if (family === 'tool') return <Terminal {...props} className="flex-none text-text-tertiary" />;
  return <Box {...props} className="flex-none text-text-tertiary" />;
}

interface CapabilityIdentityProps {
  label: CapabilityLabel;
  /** 步骤行里标题要让位给状态；审批卡片里可以更醒目。 */
  emphasis?: boolean;
  className?: string;
}

export function CapabilityIdentity({
  label,
  emphasis = false,
  className = '',
}: CapabilityIdentityProps) {
  const family = FAMILY_META[label.family];
  // unknown 分支的 title 就是原始名，再挂一枚「能力」徽章只是噪音。
  const showFamily = label.family !== 'unknown';
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="flex min-w-0 items-center gap-[6px]">
        <FamilyIcon family={label.family} />
        <span
          title={label.raw}
          className={`min-w-0 flex-1 truncate ${emphasis ? 'text-[13.5px] font-medium' : 'text-body-sm'} text-text-primary`}
        >
          {label.title}
        </span>
        {showFamily && (
          <Badge tone={family.tone} className="flex-none">
            {family.label}
          </Badge>
        )}
        {label.writes && (
          <Badge tone="warning" className="flex-none" title="该调用会写入外部状态">
            写操作
          </Badge>
        )}
      </div>
      {label.source && (
        <p className="m-0 mt-[2px] truncate pl-[18px] text-[10.5px] text-text-tertiary">
          {label.source}
        </p>
      )}
    </div>
  );
}
