import { useEffect, useRef } from 'react';
import { ArrowRight, FileText, Sparkles } from 'lucide-react';
import type { ChatMessageData, RouteEngine } from '@/types';
import { ROUTE_META } from '@/lib/routes';
import { ChatMessage } from './ChatMessage';
import { RouteBadge } from './RouteBadge';
import { ClarificationCard } from './ClarificationCard';
import { PendingActionsCard } from './PendingActionsCard';
import { ThinkingProcess } from './ThinkingProcess';
import { Markdown } from '@/components/ui/Markdown';

/** 判定分析进展是否有实质内容（兼容历史消息中的工具状态噪音）。 */
const TRIVIAL_PROGRESS_RE =
  /^(识别意图|思考中|整理结论)[…。.]*$|^调用工具\s+\S+$|^并发执行\s+\d+\s+个只读工具$|^\S+\s+(started|done)(?:\s+\d+%)?$/iu;
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
  userAvatar?: string;
  onClarifySelect?: (messageId: string, optionId: string, routeTo: RouteEngine) => void;
  /** Approve/reject a single-step business action in the conversation. */
  onActionConfirm?: (messageId: string, actionId: string, approved: boolean) => void;
}

export function Thread({
  messages,
  author = '李工',
  userAvatar,
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
              <ChatMessage
                key={m.id}
                role="user"
                author={m.author ?? author}
                timestamp={m.time}
                avatar={userAvatar}
              >
                <div>{m.text}</div>
                {((m.skills?.length ?? 0) > 0 || (m.attachments?.length ?? 0) > 0) && (
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-white/15 pt-2 text-[11px] leading-4 text-white/80">
                    {m.skills?.map((skill) => (
                      <span key={skill} className="inline-flex min-w-0 items-center gap-1">
                        <Sparkles size={11} className="shrink-0" />
                        <span className="truncate">{skill}</span>
                      </span>
                    ))}
                    {m.attachments?.map((file) => (
                      <span key={file.name} className="inline-flex min-w-0 items-center gap-1">
                        <FileText size={11} className="shrink-0" />
                        <span className="max-w-[220px] truncate">{file.name}</span>
                      </span>
                    ))}
                  </div>
                )}
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
              {/* 分析进展：只展示面向用户的判断与行动理由，不展示工具生命周期日志。 */}
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
