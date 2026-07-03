import { useEffect, useRef, useState } from 'react';
import {
  Boxes,
  SquarePen,
  Settings,
  Sun,
  Moon,
  Check,
  MoreVertical,
  Pencil,
  Trash2,
  X,
  PanelLeftClose,
} from 'lucide-react';
import type { ConversationSummary } from '@/mocks/session';
import type { Theme } from '@/stores';
import { ROUTE_META } from '@/lib/routes';

/**
 * Sidebar — the left rail: brand mark, a "new conversation" action, the
 * conversation history list, and a user/settings footer. Each history row has a
 * kebab menu (rename inline / delete); the brand header carries a collapse
 * toggle. Presentational; all mutations are driven by callbacks from the parent.
 */
interface SidebarProps {
  appName: string;
  user: string;
  role: string;
  conversations: ConversationSummary[];
  activeId: string;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
  onRenameSession: (id: string, title: string) => void;
  onDeleteSession: (id: string) => void;
  onCollapse: () => void;
  theme: Theme;
  onSetTheme: (theme: Theme) => void;
}

export function Sidebar({
  appName,
  user,
  role,
  conversations,
  activeId,
  onSelect,
  onNewConversation,
  onRenameSession,
  onDeleteSession,
  onCollapse,
  theme,
  onSetTheme,
}: SidebarProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
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
    <aside className="flex w-sidebar flex-none flex-col border-r border-border-subtle bg-bg-sunken">
      {/* Brand */}
      <div className="flex h-header flex-none items-center gap-[10px] border-b border-border-subtle px-4">
        <span className="grid h-7 w-7 flex-none place-items-center rounded-md border border-accent-border bg-accent-bg text-accent-fg shadow-glow-accent-sm">
          <Boxes size={16} />
        </span>
        <div className="flex min-w-0 flex-col leading-none">
          <span className="text-body-sm font-semibold text-text-primary">{appName}</span>
          <span className="mt-[3px] text-[10px] tracking-eyebrow text-text-tertiary">
            生产排产调度 Agent
          </span>
        </div>
        <button
          title="折叠侧栏"
          onClick={onCollapse}
          className="ml-auto grid h-[28px] w-[28px] flex-none place-items-center rounded-md text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-1 hover:text-text-secondary"
        >
          <PanelLeftClose size={16} />
        </button>
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
            const dot = c.engine
              ? (ROUTE_META[c.engine]?.dot ?? 'bg-text-tertiary')
              : 'bg-text-tertiary';
            const menuOpen = menuOpenId === c.id;
            return (
              <div
                key={c.id}
                className={`group relative flex items-center rounded-md pr-1 transition-colors duration-fast ease-out ${
                  active
                    ? 'bg-surface-2 text-text-primary'
                    : 'text-text-secondary hover:bg-surface-1'
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
                    className="mx-1 my-[2px] min-w-0 flex-1 rounded bg-surface-inset px-2 py-[6px] text-body-sm text-text-primary outline-none ring-1 ring-accent-border"
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
                      className={`grid h-[26px] w-[24px] flex-none place-items-center rounded text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-secondary ${
                        menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                    >
                      <MoreVertical size={15} />
                    </button>
                  </>
                )}
                {menuOpen && (
                  <div
                    ref={rowMenuRef}
                    className="absolute right-1 top-[34px] z-50 w-[168px] overflow-hidden rounded-lg border border-border-default bg-surface-2 py-1 shadow-popover"
                  >
                    {confirmingDelete ? (
                      <>
                        <span className="block px-3 pb-1 pt-1.5 text-caption text-text-secondary">
                          确认删除该会话？
                        </span>
                        <button
                          onClick={() => {
                            setMenuOpenId(null);
                            setConfirmingDelete(false);
                            onDeleteSession(c.id);
                          }}
                          className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-body-sm font-semibold text-status-error transition-colors duration-fast ease-out hover:bg-status-error-bg"
                        >
                          <Trash2 size={14} className="flex-none" />
                          确认删除
                        </button>
                        <button
                          onClick={() => setConfirmingDelete(false)}
                          className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-body-sm text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary"
                        >
                          <X size={14} className="flex-none text-text-tertiary" />
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => startRename(c)}
                          className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-body-sm text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary"
                        >
                          <Pencil size={14} className="flex-none text-text-tertiary" />
                          重命名
                        </button>
                        <button
                          onClick={() => setConfirmingDelete(true)}
                          className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-body-sm text-status-error transition-colors duration-fast ease-out hover:bg-status-error-bg"
                        >
                          <Trash2 size={14} className="flex-none" />
                          删除
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
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
        <div ref={settingsRef} className="relative flex-none">
          <button
            title="设置"
            onClick={() => setSettingsOpen((v) => !v)}
            className={`grid h-[30px] w-[30px] place-items-center rounded-md transition-colors duration-fast ease-out hover:bg-surface-1 hover:text-text-secondary ${
              settingsOpen ? 'bg-surface-1 text-text-secondary' : 'text-text-tertiary'
            }`}
          >
            <Settings size={16} />
          </button>
          {settingsOpen && (
            <div className="absolute bottom-[38px] right-0 z-50 w-[168px] overflow-hidden rounded-lg border border-border-default bg-surface-2 py-1 shadow-popover">
              <span className="block px-3 pb-1 pt-1.5 text-micro font-semibold uppercase text-text-tertiary">
                外观
              </span>
              {[
                { value: 'light' as const, label: '浅色', Icon: Sun },
                { value: 'dark' as const, label: '深色', Icon: Moon },
              ].map(({ value, label, Icon }) => (
                <button
                  key={value}
                  onClick={() => {
                    onSetTheme(value);
                    setSettingsOpen(false);
                  }}
                  className="flex w-full items-center gap-[9px] px-3 py-[7px] text-left text-body-sm text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary"
                >
                  <Icon size={15} className="flex-none text-text-tertiary" />
                  <span className="flex-1">{label}</span>
                  {theme === value && <Check size={14} className="flex-none text-accent-fg" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
