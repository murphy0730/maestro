import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

/**
 * ThinkingProcess — concise, user-facing reasoning summaries.
 *
 * Collapsed (default): a two-line viewport that auto-scrolls so the newest
 * lines stay visible while streaming. Expanded: the full trace, scrollable.
 * Rendered both during streaming and on committed turns. This deliberately
 * shows auditable rationale rather than private chain-of-thought or tool logs.
 */
interface ThinkingProcessProps {
  lines: string[];
  /** Streaming turns pulse the indicator dot. */
  streaming?: boolean;
}

export function ThinkingProcess({ lines, streaming = false }: ThinkingProcessProps) {
  const [expanded, setExpanded] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  // Keep the newest lines in view while collapsed (2-line rolling window).
  useEffect(() => {
    const el = viewportRef.current;
    if (el && !expanded) el.scrollTop = el.scrollHeight;
  }, [lines, expanded]);

  if (lines.length === 0) return null;
  const canExpand = lines.length > 2;

  return (
    <div className="mb-[11px] rounded-md border border-border bg-surface-2 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-caption font-medium text-text-tertiary">
          <span
            className={`h-[6px] w-[6px] rounded-full bg-accent ${streaming ? 'animate-pulse' : ''}`}
          />
          分析进展
          {streaming && ' · 处理中'}
        </span>
        {canExpand && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? '收起分析进展' : '展开分析进展'}
            className="flex items-center gap-1 rounded-md px-1 py-0.5 text-caption text-text-tertiary transition-colors hover:text-text-primary"
          >
            {expanded ? '收起' : `查看全部 ${lines.length} 条`}
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        )}
      </div>
      <div
        ref={viewportRef}
        className={`mt-1 text-caption leading-[18px] text-text-tertiary ${
          expanded ? 'max-h-[240px] overflow-y-auto' : 'max-h-[36px] overflow-hidden'
        }`}
      >
        {lines.map((line, i) => (
          <p key={`${line}-${i}`} className="m-0 flex gap-2 whitespace-pre-wrap break-words">
            <span className="select-none text-text-tertiary/60">·</span>
            <span>{line}</span>
          </p>
        ))}
      </div>
    </div>
  );
}
