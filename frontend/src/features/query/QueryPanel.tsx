import { Link, Sparkles, Copy } from 'lucide-react';
import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { AuthAction } from '@/components/ui/AuthAction';
import { EngineStrip, SectionLabel } from '@/components/ui/panel';
import {
  QUERY_PANEL,
  type AnswerSegment as AnswerSegmentData,
  type QuerySource,
} from '@/mocks/panels';

function AnswerSegment({ type, cite, text }: AnswerSegmentData) {
  const grounded = type === 'grounded';
  return (
    <div
      className={`mb-2 rounded-sm py-[9px] pl-[13px] pr-3 ${
        grounded
          ? 'border-l-2 border-l-query bg-query-bg'
          : 'border-l-2 border-dashed border-l-text-disabled bg-surface-inset'
      }`}
    >
      <div className="text-body-sm leading-relaxed text-text-primary">
        {text}
        {grounded && cite && (
          <sup className="ml-[3px]">
            {cite.map((n) => (
              <span
                key={n}
                className="ml-[2px] rounded-xs border border-query-border bg-query-bg px-[3px] font-mono text-[9px] font-bold text-query-fg"
              >
                {n}
              </span>
            ))}
          </sup>
        )}
      </div>
      <div
        className={`mt-[5px] inline-flex items-center gap-[5px] text-[9.5px] font-semibold tracking-wide ${
          grounded ? 'text-query-fg' : 'text-text-tertiary'
        }`}
      >
        {grounded ? <Link size={10} /> : <Sparkles size={10} />}
        {grounded ? '有来源 · 检索支撑' : '模型推断 · 无直接来源'}
      </div>
    </div>
  );
}

function SourceCard({ index, title, snippet, meta, score }: QuerySource) {
  const pct = Math.round(score * 100);
  return (
    <div className="rounded-md border border-border-default bg-surface-inset p-3">
      <div className="mb-[7px] flex items-center gap-2">
        <span className="grid h-[18px] w-[18px] flex-none place-items-center rounded-xs border border-query-border bg-query-bg font-mono text-[11px] font-semibold text-query-fg">
          {index}
        </span>
        <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-body-sm font-semibold text-text-primary">
          {title}
        </span>
        <span className="font-mono text-micro font-semibold text-query">{pct}%</span>
      </div>
      <div className="border-l-2 border-border-strong pl-[9px] text-caption leading-normal text-text-secondary">
        {snippet}
      </div>
      <div className="mt-2 font-mono text-micro text-text-tertiary">{meta}</div>
    </div>
  );
}

interface PanelProps {
  onClose?: () => void;
}

export function QueryPanel({ onClose }: PanelProps) {
  const d = QUERY_PANEL;
  return (
    <ContextPanel
      eyebrow={d.eyebrow}
      title={d.title}
      badge={
        <Badge tone="query" dot glow>
          查询
        </Badge>
      }
      onClose={onClose}
      footer={
        <>
          <div className="flex gap-[10px]">
            <button className="inline-flex h-[38px] flex-1 cursor-pointer items-center justify-center gap-[7px] rounded-md border border-border-default bg-surface-3 text-body font-semibold text-text-secondary">
              <Copy size={14} />
              引用回答
            </button>
            <AuthAction level="auto" compact className="flex-1">
              导出溯源报告
            </AuthAction>
          </div>
          <div className="flex items-center gap-[6px] text-[11px] text-auth-auto">
            <ShieldDot />
            只读查询 · 可直接执行，不写入排程。
          </div>
        </>
      }
    >
      <EngineStrip route="query" title={d.strip.title} meta={d.strip.meta} />

      <div>
        <SectionLabel
          right={
            <span className="inline-flex items-center gap-[5px] text-[10px] font-semibold text-query-fg">
              <span className="h-[6px] w-[6px] rounded-full bg-query shadow-glow-query" />
              RAG 检索增强
            </span>
          }
        >
          回答
        </SectionLabel>
        {d.answer.map((a, i) => (
          <AnswerSegment key={i} {...a} />
        ))}
      </div>

      <div>
        <SectionLabel
          right={
            <span className="font-mono text-[10.5px] text-text-tertiary">2 命中 / 4 检索</span>
          }
        >
          来源溯源
        </SectionLabel>
        <div className="flex flex-col gap-2">
          {d.sources.map((s) => (
            <SourceCard key={s.index} {...s} />
          ))}
        </div>
      </div>
    </ContextPanel>
  );
}

function ShieldDot() {
  return <span className="h-[6px] w-[6px] rounded-full bg-auth-auto" />;
}
