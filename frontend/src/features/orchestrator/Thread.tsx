import { useEffect, useRef } from 'react';
import { ArrowRight } from 'lucide-react';
import type { ChatMessageData, RouteEngine } from '@/types';
import { ROUTE_META } from '@/lib/routes';
import { ChatMessage } from './ChatMessage';
import { RouteBadge } from './RouteBadge';
import { ClarificationCard } from './ClarificationCard';
import { PendingActionsCard } from './PendingActionsCard';
import { ThinkingProcess } from './ThinkingProcess';
import { Markdown } from '@/components/ui/Markdown';

/** 判定思考过程是否有实质内容（非纯进度噪音）。
 *  纯 "思考中…" / "整理结论…" / "调用工具 xxx" 这类自动生成的进度行
 *  对用户无信息量；只要混入一行 LLM 自由思考文本就视为有实质内容。
 */
const TRIVIAL_PROGRESS_RE = /^(思考中…|整理结论…|调用工具\s+\S+)$/u;
function hasSubstantiveThinking(lines: string[]): boolean {
  return lines.some((l) => !TRIVIAL_PROGRESS_RE.test(l.trim()));
}

/**
 * Thread — renders a conversation. Clarification selection is lifted to the
 * parent via `onClarifySelect(messageId, optionId, routeTo)`; the picked
 * option is read from each message's own `selectedOptionId`.
 */
interface ThreadProps {
  messages: ChatMessageData[];
  author?: string;
  onClarifySelect?: (messageId: string, optionId: string, routeTo: RouteEngine) => void;
  /** Approve/reject a pending write action (wired to `POST /chat/confirm`). */
  onActionConfirm?: (messageId: string, actionId: string, approved: boolean) => void;
}

export function Thread({
  messages,
  author = '李工',
  onClarifySelect,
  onActionConfirm,
}: ThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Keep the latest message in view as the thread grows / streams.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-[30px] pb-[150px] pt-6">
      <div className="mx-auto flex min-h-full max-w-[760px] flex-col justify-end gap-[18px]">
        {messages.map((m) => {
          if (m.kind === 'system') {
            return (
              <ChatMessage key={m.id} role="system">
                {m.text}
              </ChatMessage>
            );
          }
          if (m.kind === 'user') {
            return (
              <ChatMessage key={m.id} role="user" author={m.author ?? author} timestamp={m.time}>
                {m.text}
              </ChatMessage>
            );
          }
          if (m.kind === 'clarify') {
            return (
              <ChatMessage key={m.id} role="agent" author="Maestro" timestamp={m.time}>
                <div className="mb-[11px]">
                  <RouteBadge route="uncertain" confidence={m.confidence} reason={m.reason} />
                </div>
                <ClarificationCard
                  question={m.question}
                  detail={m.detail}
                  options={m.options}
                  selectedId={m.selectedOptionId ?? null}
                  onSelect={(optionId) => {
                    const opt = m.options.find((o) => o.id === optionId);
                    onClarifySelect?.(m.id, optionId, opt?.route ?? 'uncertain');
                  }}
                />
              </ChatMessage>
            );
          }
          // agent
          return (
            <ChatMessage key={m.id} role="agent" author="Maestro" timestamp={m.time}>
              {m.route && (
                <div className="mb-[11px]">
                  <RouteBadge
                    route={m.route}
                    confidence={m.confidence}
                    reason={m.reason}
                    slash={m.slash}
                    slashCmd={m.slashCmd}
                  />
                </div>
              )}
              {/* 思考过程：流式中始终展示；完成后仅在有实质内容时保留 */}
              {m.thinking &&
                m.thinking.length > 0 &&
                (m.streaming || hasSubstantiveThinking(m.thinking)) && (
                  <ThinkingProcess lines={m.thinking} streaming={m.streaming} />
                )}
              {m.text && (
                <div className="text-body leading-relaxed">
                  <Markdown>{m.text}</Markdown>
                  {m.streaming && (
                    <span className="ml-[3px] inline-block h-[14px] w-[2px] animate-pulse rounded-pill bg-accent align-middle" />
                  )}
                </div>
              )}
              {m.streaming && !m.text && !(m.thinking && m.thinking.length > 0) && (
                <p className="m-0 flex items-center gap-2 leading-relaxed text-text-tertiary">
                  <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-accent" />
                  {m.progress ?? '正在分析意图…'}
                </p>
              )}
              {m.pendingActions && m.pendingActions.length > 0 && (
                <PendingActionsCard
                  actions={m.pendingActions}
                  onConfirm={(actionId, approved) => onActionConfirm?.(m.id, actionId, approved)}
                />
              )}
              {m.handoff && m.route && (
                <div
                  className={`mt-[11px] flex items-center gap-2 text-caption ${ROUTE_META[m.route].fg}`}
                >
                  <ArrowRight size={14} strokeWidth={2} />
                  方案已生成 · 详见右侧上下文面板
                </div>
              )}
            </ChatMessage>
          );
        })}
      </div>
    </div>
  );
}
