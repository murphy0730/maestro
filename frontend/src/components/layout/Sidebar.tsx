import { useEffect, useRef, useState } from 'react';
import {
  ListChecks,
  SquarePen,
  Settings,
  Sun,
  Moon,
  Sparkles,
  Check,
  ChevronRight,
  ChevronLeft,
  Palette,
  MoreVertical,
  Cpu,
  UserRoundCog,
  Pencil,
  Trash2,
  X,
  PanelLeftClose,
} from 'lucide-react';
import type { ConversationSummary } from '@/mocks/session';
import type { Theme, DefaultEngine } from '@/stores';
import { ROUTE_META } from '@/lib/routes';
import { Popover, PopoverItem, PopoverLabel } from '@/components/ui/Popover';
import { BatonIcon } from '@/components/ui/Icon';
import { SettingsModal } from '@/features/orchestrator/settings/SettingsModal';
import { PersonalizationModal } from '@/features/orchestrator/settings/PersonalizationModal';

// 本地引擎选项常量（避免跨 layer 依赖 Composer）
const ENGINE_OPTS: { value: DefaultEngine; label: string; dot: string }[] = [
  { value: 'auto', label: '自动', dot: 'bg-accent' },
  { value: 'planning', label: '排产', dot: 'bg-planning' },
  { value: 'scheduling', label: '调度', dot: 'bg-scheduling' },
  { value: 'query', label: '查询', dot: 'bg-query' },
];

/**
 * Sidebar — the left rail: brand mark, a "new conversation" action, the
 * conversation history list, and a user/settings footer. Each history row has a
 * kebab menu (rename inline / delete); the brand header carries a collapse
 * toggle. Presentational; all mutations are driven by callbacks from the parent.
 */
interface SidebarProps {
  appName: string;
  user: string;
  /** Avatar letter. Latin names derive it from `user`; CJK names must pass it
   *  explicitly (there is no letter to take the first character of). */
  initial?: string;
  role: string;
  conversations: ConversationSummary[];
  activeId: string;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
  /** Navigate to the task list. Omitted (e.g. in tests) hides the entry. */
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsView, setSettingsView] = useState<'root' | 'engine'>('root');
  const [modelOpen, setModelOpen] = useState(false);
  const [personalizationOpen, setPersonalizationOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  // 会话行的操作菜单 / 内联重命名状态
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const rowMenuRef = useRef<HTMLDivElement>(null);

  const openRowMenu = (id: string) => {
    setConfirmingDelete(false);
    setMenuOpenId((cur) => (cur === id ? null : id));
  };

  // 点击外部关闭设置菜单
  useEffect(() => {
    if (!settingsOpen) return;
    const onClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
        setSettingsView('root');
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [settingsOpen]);

  // 点击外部关闭会话操作菜单
  useEffect(() => {
    if (!menuOpenId) return;
    const onClick = (e: MouseEvent) => {
      if (rowMenuRef.current && !rowMenuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [menuOpenId]);

  const startRename = (c: ConversationSummary) => {
    setMenuOpenId(null);
    setEditingId(c.id);
    setEditValue(c.title);
  };

  const commitRename = (c: ConversationSummary) => {
    const next = editValue.trim();
    if (next && next !== c.title) onRenameSession(c.id, next);
    setEditingId(null);
  };

  return (
    <aside className="material-chrome flex w-sidebar flex-none flex-col border-r border-border-subtle">
      {/* Brand — the baton mark plus a wordmark with room to breathe. The
          wordmark uses looser tracking than headings: at 15px, Geist 600 at
          -0.02em nearly glues the letters together. */}
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

      {/* New conversation */}
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

      {/* History */}
      <div className="flex min-h-0 flex-1 flex-col">
        <span className="flex-none px-4 pb-2 pt-1 text-micro font-semibold uppercase text-text-tertiary">
          历史对话
        </span>
        <nav className="min-h-0 flex-1 space-y-[2px] overflow-y-auto px-2">
          {conversations.map((c) => {
            const active = c.id === activeId;
            const dot = c.engine
              ? (ROUTE_META[c.engine]?.dot ?? 'bg-text-tertiary')
              : 'bg-text-tertiary';
            const menuOpen = menuOpenId === c.id;
            return (
              <div
                key={c.id}
                className={`group relative flex items-center rounded-sm pr-1 transition-colors duration-fast ease-out ${
                  active
                    ? 'bg-accent-bg text-text-primary ring-1 ring-inset ring-accent-border'
                    : 'text-text-secondary hover:bg-surface-2'
                }`}
              >
                {editingId === c.id ? (
                  <input
                    autoFocus
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename(c);
                      else if (e.key === 'Escape') setEditingId(null);
                    }}
                    onBlur={() => commitRename(c)}
                    className="mx-1 my-[2px] min-w-0 flex-1 rounded-sm bg-surface-1 px-2 py-[6px] text-body-sm text-text-primary outline-none ring-1 ring-accent-border"
                  />
                ) : (
                  <>
                    <button
                      onClick={() => onSelect(c.id)}
                      className="flex min-w-0 flex-1 items-center gap-[9px] px-2 py-[7px] text-left"
                    >
                      <span className={`h-[6px] w-[6px] flex-none rounded-full ${dot}`} />
                      <span className="min-w-0 flex-1 truncate text-body-sm">{c.title}</span>
                      <span className="flex-none font-mono text-[10px] text-text-tertiary">
                        {c.time}
                      </span>
                    </button>
                    <button
                      title="更多"
                      onClick={() => openRowMenu(c.id)}
                      className={`grid h-[26px] w-[24px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary ${
                        menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                    >
                      <MoreVertical size={15} />
                    </button>
                  </>
                )}
                {menuOpen && (
                  <div ref={rowMenuRef}>
                    <Popover className="absolute right-1 top-[34px] w-[168px]">
                      {confirmingDelete ? (
                        <>
                          <span className="block px-3 pb-1 pt-1.5 text-caption text-text-secondary">
                            确认删除该会话？
                          </span>
                          <PopoverItem
                            tone="danger"
                            icon={<Trash2 size={14} />}
                            className="font-semibold"
                            onClick={() => {
                              setMenuOpenId(null);
                              setConfirmingDelete(false);
                              onDeleteSession(c.id);
                            }}
                          >
                            确认删除
                          </PopoverItem>
                          <PopoverItem
                            icon={<X size={14} />}
                            onClick={() => setConfirmingDelete(false)}
                          >
                            取消
                          </PopoverItem>
                        </>
                      ) : (
                        <>
                          <PopoverItem icon={<Pencil size={14} />} onClick={() => startRename(c)}>
                            重命名
                          </PopoverItem>
                          <PopoverItem
                            tone="danger"
                            icon={<Trash2 size={14} />}
                            onClick={() => setConfirmingDelete(true)}
                          >
                            删除
                          </PopoverItem>
                        </>
                      )}
                    </Popover>
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      {/* User + settings */}
      <div className="flex flex-none items-center gap-[9px] border-t border-border-subtle px-3 py-3">
        <span className="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-blue-solid font-display text-caption font-semibold text-on-solid">
          {initial ?? user.trim().charAt(0).toUpperCase()}
        </span>
        <div className="flex min-w-0 flex-1 flex-col leading-none">
          <span className="truncate text-body-sm font-medium text-text-primary">{user}</span>
          <span className="mt-[3px] truncate text-caption text-text-tertiary">{role}</span>
        </div>
        <div ref={settingsRef} className="relative flex-none">
          <button
            title="设置"
            onClick={() => {
              setSettingsOpen((v) => !v);
              setSettingsView('root');
            }}
            className={`grid h-[30px] w-[30px] place-items-center rounded-sm transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary ${
              settingsOpen ? 'bg-border-subtle text-text-secondary' : 'text-text-tertiary'
            }`}
          >
            <Settings size={16} />
          </button>
          {settingsOpen && (
            <Popover className="absolute bottom-[38px] right-0 w-[200px]">
              {settingsView === 'root' && (
                <>
                  <PopoverLabel>设置</PopoverLabel>
                  {/* 外观：行内深色/浅色切换，无需二次菜单 */}
                  <div className="flex w-full items-center gap-2 px-3 py-[7px]">
                    <span className="flex-none text-text-tertiary">
                      <Palette size={15} />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-body-sm text-text-secondary">
                      外观
                    </span>
                    <div className="flex flex-none items-center rounded-md border border-border-default bg-surface-1 p-[2px]">
                      <button
                        type="button"
                        title="浅色"
                        aria-label="浅色"
                        aria-pressed={theme === 'light'}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSetTheme('light');
                        }}
                        className={`grid h-[22px] w-[22px] place-items-center rounded-[5px] transition-colors ${
                          theme === 'light'
                            ? 'bg-surface-3 text-text-primary'
                            : 'text-text-tertiary hover:text-text-secondary'
                        }`}
                      >
                        <Sun size={13} />
                      </button>
                      <button
                        type="button"
                        title="深色"
                        aria-label="深色"
                        aria-pressed={theme === 'dark'}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSetTheme('dark');
                        }}
                        className={`grid h-[22px] w-[22px] place-items-center rounded-[5px] transition-colors ${
                          theme === 'dark'
                            ? 'bg-surface-3 text-text-primary'
                            : 'text-text-tertiary hover:text-text-secondary'
                        }`}
                      >
                        <Moon size={13} />
                      </button>
                    </div>
                  </div>
                  <PopoverItem
                    icon={<Sparkles size={15} />}
                    trailing={<ChevronRight size={14} className="flex-none text-text-tertiary" />}
                    onClick={() => setSettingsView('engine')}
                  >
                    默认引擎
                  </PopoverItem>
                  <PopoverItem
                    icon={<Cpu size={15} />}
                    onClick={() => {
                      setSettingsOpen(false);
                      setModelOpen(true);
                    }}
                  >
                    模型
                  </PopoverItem>
                  <PopoverItem
                    icon={<UserRoundCog size={15} />}
                    onClick={() => {
                      setSettingsOpen(false);
                      setPersonalizationOpen(true);
                    }}
                  >
                    个性化
                  </PopoverItem>
                </>
              )}

              {settingsView === 'engine' && (
                <>
                  <PopoverItem
                    icon={<ChevronLeft size={14} />}
                    onClick={() => setSettingsView('root')}
                  >
                    默认引擎
                  </PopoverItem>
                  {ENGINE_OPTS.map(({ value, label, dot }) => (
                    <PopoverItem
                      key={value}
                      icon={<span className={`h-[7px] w-[7px] rounded-full ${dot}`} />}
                      trailing={
                        defaultEngine === value ? (
                          <Check size={14} className="flex-none text-accent-fg" />
                        ) : undefined
                      }
                      onClick={() => {
                        onSetDefaultEngine(value);
                        setSettingsView('root');
                      }}
                    >
                      {label}
                    </PopoverItem>
                  ))}
                </>
              )}
            </Popover>
          )}
        </div>
      </div>

      <SettingsModal open={modelOpen} onClose={() => setModelOpen(false)} />
      <PersonalizationModal
        open={personalizationOpen}
        onClose={() => setPersonalizationOpen(false)}
      />
    </aside>
  );
}
