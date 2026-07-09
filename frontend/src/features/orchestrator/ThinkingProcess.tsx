import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

/**
 * ThinkingProcess — the agent's live thinking/progress trace.
 *
 * Collapsed (default): a two-line viewport that auto-scrolls so the newest
 * lines stay visible while streaming. Expanded: the full trace, scrollable.
 * Rendered both during streaming and on committed turns so the reasoning is
 * never a black box.
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

  return (
    <div className="mb-[11px] rounded-md border border-border bg-surface-2 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-caption font-medium text-text-tertiary">
          <span
            className={`h-[6px] w-[6px] rounded-full bg-accent ${streaming ? 'animate-pulse' : ''}`}
          />
          思考过程
          {streaming && lines.length > 0 && `（${lines.length} 步）`}
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={expanded ? '收起思考过程' : '展开思考过程'}
          className="flex items-center gap-1 rounded-md px-1 py-0.5 text-caption text-text-tertiary transition-colors hover:text-text-primary"
        >
          {expanded ? '收起' : '展开'}
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>
      <div
        ref={viewportRef}
        className={`mt-1 text-caption leading-[18px] text-text-tertiary ${
          expanded ? 'max-h-[240px] overflow-y-auto' : 'max-h-[36px] overflow-hidden'
        }`}
      >
        {lines.map((line, i) => (
          <p key={i} className="m-0 whitespace-pre-wrap break-words">
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}
