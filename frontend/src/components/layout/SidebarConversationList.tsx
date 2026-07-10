import { useEffect, useRef, useState } from 'react';
import { MoreVertical, Pencil, Trash2, X } from 'lucide-react';
import type { ConversationSummary } from '@/mocks/session';
import { ROUTE_META } from '@/lib/routes';
import { Popover, PopoverItem } from '@/components/ui/Popover';

interface SidebarConversationListProps {
  conversations: ConversationSummary[];
  activeId: string;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
  onSelect: (id: string) => void;
}

export function SidebarConversationList({
  conversations,
  activeId,
  onDeleteSession,
  onRenameSession,
  onSelect,
}: SidebarConversationListProps) {
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const rowMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpenId) return;
    const onClick = (event: MouseEvent) => {
      if (rowMenuRef.current && !rowMenuRef.current.contains(event.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [menuOpenId]);

  const openRowMenu = (id: string) => {
    setConfirmingDelete(false);
    setMenuOpenId((current) => (current === id ? null : id));
  };

  const startRename = (conversation: ConversationSummary) => {
    setMenuOpenId(null);
    setEditingId(conversation.id);
    setEditValue(conversation.title);
  };

  const commitRename = (conversation: ConversationSummary) => {
    const next = editValue.trim();
    if (next && next !== conversation.title) onRenameSession(conversation.id, next);
    setEditingId(null);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <span className="flex-none px-4 pb-2 pt-1 text-micro font-semibold uppercase text-text-tertiary">
        历史对话
      </span>
      <nav className="min-h-0 flex-1 space-y-[2px] overflow-y-auto px-2">
        {conversations.map((conversation) => {
          const active = conversation.id === activeId;
          const dot = conversation.engine
            ? (ROUTE_META[conversation.engine]?.dot ?? 'bg-text-tertiary')
            : 'bg-text-tertiary';
          const menuOpen = menuOpenId === conversation.id;
          return (
            <div
              key={conversation.id}
              className={`group relative flex items-center rounded-sm pr-1 transition-colors duration-fast ease-out ${
                active
                  ? 'bg-accent-bg text-text-primary ring-1 ring-inset ring-accent-border'
                  : 'text-text-secondary hover:bg-surface-2'
              }`}
            >
              {editingId === conversation.id ? (
                <input
                  autoFocus
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') commitRename(conversation);
                    else if (event.key === 'Escape') setEditingId(null);
                  }}
                  onBlur={() => commitRename(conversation)}
                  className="mx-1 my-[2px] min-w-0 flex-1 rounded-sm bg-surface-1 px-2 py-[6px] text-body-sm text-text-primary outline-none ring-1 ring-accent-border"
                />
              ) : (
                <>
                  <button
                    onClick={() => onSelect(conversation.id)}
                    className="flex min-w-0 flex-1 items-center gap-[9px] px-2 py-[7px] text-left"
                  >
                    <span className={`h-[6px] w-[6px] flex-none rounded-full ${dot}`} />
                    <span className="min-w-0 flex-1 truncate text-body-sm">
                      {conversation.title}
                    </span>
                    <span className="flex-none font-mono text-[10px] text-text-tertiary">
                      {conversation.time}
                    </span>
                  </button>
                  <button
                    title="更多"
                    onClick={() => openRowMenu(conversation.id)}
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
                            onDeleteSession(conversation.id);
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
                        <PopoverItem
                          icon={<Pencil size={14} />}
                          onClick={() => startRename(conversation)}
                        >
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
  );
}
