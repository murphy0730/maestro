import type { ReactNode } from 'react';
import type { ChatRole } from '@/types';

/**
 * ChatMessage — conversation bubble in three forms:
 *  - user:   right-aligned, accent-tinted
 *  - agent:  left-aligned surface bubble (compose RouteBadge / cards as children)
 *  - system: full-width centered meta line (clarifications, run events)
 * Pure presentational.
 */
interface ChatMessageProps {
  role?: ChatRole;
  children: ReactNode;
  author?: string;
  timestamp?: string;
  avatar?: string;
}

export function ChatMessage({
  role = 'agent',
  children,
  author,
  timestamp,
  avatar,
}: ChatMessageProps) {
  if (role === 'system') {
    return (
      <div className="flex items-center gap-[10px] py-2 font-sans">
        <span className="h-px flex-1 bg-border-subtle" />
        <span className="whitespace-nowrap text-caption text-text-tertiary">{children}</span>
        <span className="h-px flex-1 bg-border-subtle" />
      </div>
    );
  }

  const isUser = role === 'user';
  return (
    <div className={`flex w-full gap-[14px] font-sans ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      <span
        className={`grid h-7 w-7 flex-none place-items-center rounded-sm border text-caption font-bold ${
          isUser
            ? 'border-border-default bg-surface-3 text-text-secondary'
            : 'border-accent-border bg-accent-bg text-accent-fg shadow-glow-accent-sm'
        }`}
      >
        {avatar ?? (isUser ? 'You' : 'AI')}
      </span>
      <div className={`flex min-w-0 flex-1 flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        {(author || timestamp) && (
          <div className="flex gap-2 px-[2px] text-micro text-text-tertiary">
            {author && <span className="font-semibold text-text-secondary">{author}</span>}
            {timestamp && <span className="font-mono">{timestamp}</span>}
          </div>
        )}
        <div
          className={`rounded-lg border px-[13px] py-[10px] text-body leading-normal text-text-primary shadow-elev-1 ${
            isUser ? 'border-accent-border bg-accent-bg' : 'border-border-default bg-surface-1'
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
