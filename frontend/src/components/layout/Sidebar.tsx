import { Boxes, SquarePen, Settings, MoreHorizontal } from 'lucide-react';
import type { ConversationSummary } from '@/mocks/session';
import { ROUTE_META } from '@/lib/routes';

/**
 * Sidebar — the left rail: brand mark, a "new conversation" action, the
 * conversation history list, and a user/settings footer. Pure presentational;
 * selection + new-conversation are driven by callbacks from the parent.
 */
interface SidebarProps {
  appName: string;
  user: string;
  role: string;
  conversations: ConversationSummary[];
  activeId: string;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
}

export function Sidebar({
  appName,
  user,
  role,
  conversations,
  activeId,
  onSelect,
  onNewConversation,
}: SidebarProps) {
  return (
    <aside className="flex w-sidebar flex-none flex-col border-r border-border-subtle bg-bg-sunken">
      {/* Brand */}
      <div className="flex h-header flex-none items-center gap-[10px] border-b border-border-subtle px-4">
        <span className="grid h-7 w-7 place-items-center rounded-md border border-accent-border bg-accent-bg text-accent-fg shadow-glow-accent-sm">
          <Boxes size={16} />
        </span>
        <div className="flex min-w-0 flex-col leading-none">
          <span className="text-body-sm font-semibold text-text-primary">{appName}</span>
          <span className="mt-[3px] text-[10px] tracking-eyebrow text-text-tertiary">
            生产排产调度 Agent
          </span>
        </div>
      </div>

      {/* New conversation */}
      <div className="flex-none p-3">
        <button
          onClick={onNewConversation}
          className="inline-flex h-[34px] w-full items-center justify-center gap-[7px] rounded-md border border-border-default bg-surface-2 text-body-sm font-semibold text-text-primary shadow-inset-top-hi transition-colors duration-fast ease-out hover:bg-surface-3"
        >
          <SquarePen size={15} />
          新建对话
        </button>
      </div>

      {/* History */}
      <div className="flex min-h-0 flex-1 flex-col">
        <span className="flex-none px-4 pb-2 pt-1 text-micro font-semibold uppercase text-text-tertiary">
          历史对话
        </span>
        <nav className="min-h-0 flex-1 space-y-[2px] overflow-y-auto px-2">
          {conversations.map((c) => {
            const active = c.id === activeId;
            const dot = ROUTE_META[c.engine].dot;
            return (
              <button
                key={c.id}
                onClick={() => onSelect(c.id)}
                className={`group flex w-full items-center gap-[9px] rounded-md px-2 py-[7px] text-left transition-colors duration-fast ease-out ${
                  active
                    ? 'bg-surface-2 text-text-primary'
                    : 'text-text-secondary hover:bg-surface-1'
                }`}
              >
                <span className={`h-[6px] w-[6px] flex-none rounded-full ${dot}`} />
                <span className="min-w-0 flex-1 truncate text-body-sm">{c.title}</span>
                <span className="flex-none font-mono text-[10px] text-text-tertiary">{c.time}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* User + settings */}
      <div className="flex flex-none items-center gap-[9px] border-t border-border-subtle px-3 py-3">
        <span className="grid h-8 w-8 flex-none place-items-center rounded-full border border-border-default bg-surface-2 text-body-sm font-semibold text-text-primary">
          {user.slice(0, 1)}
        </span>
        <div className="flex min-w-0 flex-1 flex-col leading-none">
          <span className="truncate text-body-sm font-semibold text-text-primary">{user}</span>
          <span className="mt-[3px] truncate text-caption text-text-tertiary">{role}</span>
        </div>
        <button
          title="更多"
          className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-1 hover:text-text-secondary"
        >
          <MoreHorizontal size={16} />
        </button>
        <button
          title="设置"
          className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-1 hover:text-text-secondary"
        >
          <Settings size={16} />
        </button>
      </div>
    </aside>
  );
}
