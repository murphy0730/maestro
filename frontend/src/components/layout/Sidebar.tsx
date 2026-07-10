import { ListChecks, PanelLeftClose, SquarePen } from 'lucide-react';
import type { ConversationSummary } from '@/mocks/session';
import type { DefaultEngine, Theme } from '@/stores';
import { BatonIcon } from '@/components/ui/Icon';
import { SidebarConversationList } from './SidebarConversationList';
import { SidebarSettings } from './SidebarSettings';

interface SidebarProps {
  appName: string;
  user: string;
  initial?: string;
  role: string;
  conversations: ConversationSummary[];
  activeId: string;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
  onOpenTasks?: () => void;
  onRenameSession: (id: string, title: string) => void;
  onDeleteSession: (id: string) => void;
  onCollapse: () => void;
  theme: Theme;
  onSetTheme: (theme: Theme) => void;
  defaultEngine: DefaultEngine;
  onSetDefaultEngine: (engine: DefaultEngine) => void;
}

export function Sidebar({
  appName,
  user,
  initial,
  role,
  conversations,
  activeId,
  onSelect,
  onNewConversation,
  onOpenTasks,
  onRenameSession,
  onDeleteSession,
  onCollapse,
  theme,
  onSetTheme,
  defaultEngine,
  onSetDefaultEngine,
}: SidebarProps) {
  return (
    <aside className="material-chrome flex w-sidebar flex-none flex-col border-r border-border-subtle">
      <div className="flex h-header flex-none items-center gap-[10px] border-b border-border-subtle px-4">
        <span className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md bg-blue-solid text-on-solid shadow-elev-1">
          <BatonIcon size={18} />
        </span>
        <div className="flex min-w-0 flex-col leading-none">
          <span className="font-display text-[15px] font-semibold tracking-[-0.005em] text-text-primary">
            {appName}
          </span>
          <span className="mt-[4px] text-[9.5px] tracking-eyebrow text-text-tertiary">
            生产排产调度 Agent
          </span>
        </div>
        <button
          title="折叠侧栏"
          onClick={onCollapse}
          className="ml-auto grid h-[28px] w-[28px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>
      <div className="flex-none p-3">
        <button
          onClick={onNewConversation}
          className="inline-flex h-control w-full items-center justify-center gap-[7px] rounded-sm bg-blue-solid text-body-sm font-medium text-on-solid shadow-elev-1 transition-colors duration-fast ease-out hover:bg-blue-solid-hover"
        >
          <SquarePen size={14} />
          新建对话
        </button>
        {onOpenTasks && (
          <button
            onClick={onOpenTasks}
            className="mt-[6px] inline-flex h-control w-full items-center gap-[9px] rounded-sm px-2 text-body-sm font-medium text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-2 hover:text-text-primary"
          >
            <ListChecks size={15} className="flex-none text-text-tertiary" />
            任务列表
          </button>
        )}
      </div>
      <SidebarConversationList
        conversations={conversations}
        activeId={activeId}
        onSelect={onSelect}
        onRenameSession={onRenameSession}
        onDeleteSession={onDeleteSession}
      />
      <SidebarSettings
        user={user}
        initial={initial}
        role={role}
        theme={theme}
        onSetTheme={onSetTheme}
        defaultEngine={defaultEngine}
        onSetDefaultEngine={onSetDefaultEngine}
      />
    </aside>
  );
}
