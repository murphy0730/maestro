import type { ReactNode } from 'react';
import type { ChatRole } from '@/types';
import { BatonIcon } from '@/components/ui/Icon';

/**
 * ChatMessage — conversation bubble in three forms:
 *  - user:   right-aligned, solid blue, white text
 *  - agent:  left-aligned surface bubble (compose RouteBadge / cards as children)
 *  - system: full-width centered meta line (clarifications, run events)
 *
 * Each bubble tucks the corner nearest its avatar (4px instead of 12px) —
 * quieter than a triangular tail, and it still points at the speaker.
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
    <div className={`flex w-full gap-3 font-sans ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      <span
        className={`grid h-[26px] w-[26px] flex-none place-items-center rounded-sm text-caption font-medium ${
          isUser
            ? 'border border-accent-border bg-accent-bg text-accent-fg'
            : 'bg-blue-solid text-on-solid'
        }`}
      >
        {avatar ??
          (isUser ? (author?.trim().charAt(0).toUpperCase() ?? 'You') : <BatonIcon size={15} />)}
      </span>
      <div className={`flex min-w-0 flex-1 flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        {(author || timestamp) && (
          <div className="flex gap-2 px-[2px] text-micro text-text-tertiary">
            {author && <span className="font-medium text-text-secondary">{author}</span>}
            {timestamp && <span className="font-mono">{timestamp}</span>}
          </div>
        )}
        <div
          className={`rounded-lg px-[13px] py-[10px] text-body leading-relaxed ${
            isUser
              ? 'rounded-br-xs bg-blue-solid text-on-solid'
              : 'rounded-bl-xs border border-border-subtle bg-surface-1 text-text-primary'
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
