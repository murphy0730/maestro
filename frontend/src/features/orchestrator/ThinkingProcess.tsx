import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { StatusDot } from '@/components/ui/StatusDot';

/**
 * ThinkingProcess — 设计稿 A 的 `.think`：一行等宽的「分析进展 · …」进度提示。
 *
 * 折叠时只显示最新一条，展开后是完整的等宽行列表。展示的是可审计的执行进展，
 * 不是模型的私有思维链。
 */
interface ThinkingProcessProps {
  lines: string[];
  /** 流式回合让状态点脉冲。 */
  streaming?: boolean;
}

export function ThinkingProcess({ lines, streaming = false }: ThinkingProcessProps) {
  const [expanded, setExpanded] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = viewportRef.current;
    if (element && expanded) element.scrollTop = element.scrollHeight;
  }, [lines, expanded]);

  if (lines.length === 0) return null;
  const canExpand = lines.length > 1;
  const latest = lines[lines.length - 1];

  return (
    <div className="mb-[8px]">
      <div className="flex items-center gap-[8px] font-mono text-[10.5px] leading-[1.9] tracking-[0.06em] text-text-tertiary">
        <StatusDot tone="accent" pulse={streaming} />
        <span className="min-w-0 flex-1 truncate">
          分析进展 · {streaming ? `${latest}…` : latest}
        </span>
        {canExpand && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            aria-label={expanded ? '收起分析进展' : '展开分析进展'}
            className="flex flex-none items-center gap-[4px] rounded-sm px-[4px] text-text-tertiary transition-colors duration-fast hover:text-accent"
          >
            {expanded ? '收起' : `全部 ${lines.length}`}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        )}
      </div>
      {expanded && (
        <div
          ref={viewportRef}
          className="mt-[4px] max-h-[240px] overflow-y-auto border-l border-border-subtle pl-[12px] font-mono text-[10.5px] leading-[1.9] text-text-tertiary"
        >
          {lines.map((line, index) => (
            <p key={`${line}-${index}`} className="m-0 whitespace-pre-wrap break-words">
              {line}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
