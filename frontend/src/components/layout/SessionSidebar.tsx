import { useMemo, useState } from 'react';
import {
  Check,
  ChevronsLeft,
  ChevronsRight,
  Grid2X2,
  Moon,
  Pencil,
  Plus,
  Search,
  Settings,
  Sun,
  Trash2,
  X,
} from 'lucide-react';
import type { SessionSummary } from '@/api/sessions';
import type { Theme } from '@/stores/themeStore';
import { Avatar } from '@/components/ui/Avatar';
import { BrandMark } from '@/components/ui/BrandMark';
import { StatusDot, type DotTone } from '@/components/ui/StatusDot';

interface Props {
  sessions: SessionSummary[];
  activeSessionId: string;
  collapsed: boolean;
  theme: Theme;
  operatorName?: string;
  loading?: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onCreate: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSkills: () => void;
  onOpenSettings: () => void;
  onToggleTheme: () => void;
  /** True while the Extensions Center route is showing, so the entry reads as selected. */
  skillsActive?: boolean;
}

function groupLabel(date: string) {
  const value = new Date(date);
  const now = new Date();
  const days = Math.floor(
    (new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() -
      new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()) /
      86400000,
  );
  if (days <= 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return '本周';
  return '更早';
}

/** 会话行右侧的等宽时间：今天显示时刻，更早显示日期 —— 只用真实的 updated_at。 */
function rowTime(date: string) {
  const value = new Date(date);
  return groupLabel(date) === '今天'
    ? value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
    : value.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

const railButton =
  'grid h-[38px] w-[38px] place-items-center rounded-[9px] text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary';
const bottomRow =
  'flex w-full items-center gap-[10px] rounded-md px-[10px] py-[7px] text-caption text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary';

/**
 * SessionSidebar — 设计稿 D：展开 264px / 折叠 56px 的会话侧栏。
 * 会话行是单行「状态点 + 标题 + 等宽时间」，选中态用左侧发光指示条；
 * 消息条数没有独立视觉位，放进可访问名与 title，避免伪造预览字段。
 */
export function SessionSidebar(props: Props) {
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<string>();
  const [title, setTitle] = useState('');
  const operatorName = props.operatorName ?? '周文涛';
  const filtered = useMemo(
    () =>
      props.sessions.filter((session) =>
        session.title.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [props.sessions, query],
  );
  const groups = useMemo(
    () =>
      filtered.reduce<Record<string, SessionSummary[]>>((result, session) => {
        const key = groupLabel(session.updated_at);
        (result[key] ??= []).push(session);
        return result;
      }, {}),
    [filtered],
  );

  if (props.collapsed) {
    return (
      <aside
        aria-label="会话导航"
        className="flex w-sidebar-rail flex-none flex-col items-center gap-[6px] border-r border-border-subtle bg-surface-1 py-[14px]"
      >
        <span className="mb-[8px] leading-none">
          <BrandMark size={24} />
        </span>
        <button
          type="button"
          aria-label="展开会话栏"
          title="展开会话栏"
          onClick={() => props.onCollapsedChange(false)}
          className={railButton}
        >
          <ChevronsRight size={17} />
        </button>
        <button
          type="button"
          aria-label="新建会话"
          title="新建会话"
          onClick={props.onCreate}
          className={railButton}
        >
          <Plus size={17} />
        </button>
        <span className="my-[4px] h-px w-[20px] bg-border-strong" />
        <button
          type="button"
          aria-label="技能管理"
          title="技能·连接器管理"
          aria-current={props.skillsActive ? 'page' : undefined}
          onClick={props.onOpenSkills}
          className={`${railButton} ${props.skillsActive ? 'bg-surface-3 text-accent' : ''}`}
        >
          <Grid2X2 size={17} />
        </button>
        <span className="flex-1" />
        <button
          type="button"
          aria-label="切换主题"
          title={props.theme === 'dark' ? '切换至极昼' : '切换至深空'}
          onClick={props.onToggleTheme}
          className={railButton}
        >
          {props.theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <Avatar name={operatorName} size={30} />
        <button
          type="button"
          aria-label="设置"
          title="设置"
          onClick={props.onOpenSettings}
          className={railButton}
        >
          <Settings size={17} />
        </button>
      </aside>
    );
  }

  return (
    <aside
      aria-label="会话导航"
      className="flex w-sidebar flex-none flex-col overflow-hidden border-r border-border-subtle bg-surface-1"
    >
      <div className="flex items-center gap-[9px] px-[14px] pb-[10px] pt-[13px]">
        <BrandMark size={23} />
        <span className="font-mono text-[11px] font-semibold tracking-[.22em] text-text-primary">
          MAESTRO
        </span>
        <button
          type="button"
          aria-label="折叠会话栏"
          title="折叠侧栏"
          onClick={() => props.onCollapsedChange(true)}
          className="ml-auto grid h-[24px] w-[24px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-accent"
        >
          <ChevronsLeft size={16} />
        </button>
      </div>

      <button
        type="button"
        onClick={props.onCreate}
        disabled={props.loading}
        className="mx-[12px] mb-[10px] flex items-center justify-center gap-[8px] rounded-md border border-border-subtle bg-surface-2 px-[14px] py-[9px] text-[12.5px] font-medium text-text-primary transition duration-normal ease-out hover:border-accent hover:text-accent hover:shadow-glow-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Plus size={15} />
        新建会话
      </button>

      <div className="px-[12px] pb-[8px]">
        <label className="flex items-center gap-[8px] rounded-md border border-border-subtle bg-surface-2 px-[12px] py-[7px] text-text-tertiary transition-colors duration-fast focus-within:border-accent">
          <Search size={13} className="flex-none" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索会话…"
            className="min-w-0 flex-1 bg-transparent text-caption text-text-primary outline-none placeholder:text-text-tertiary"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-[8px] pb-[12px]">
        {Object.entries(groups).map(([group, items]) => (
          <section key={group} aria-label={group}>
            <h2 className="hud-label mb-[6px] mt-[12px] px-[4px] text-text-tertiary">{group}</h2>
            {items.map((session) => {
              const active = session.session_id === props.activeSessionId;
              const running = Boolean(session.active_run_id);
              const tone: DotTone = running ? 'warning' : active ? 'accent' : 'success';
              return (
                <div
                  key={session.session_id}
                  className={`group relative flex items-center gap-[9px] rounded-[9px] px-[10px] py-[8px] transition-colors duration-fast ease-out ${active ? 'edge-marker bg-surface-3' : 'hover:bg-surface-3'}`}
                >
                  <StatusDot tone={tone} pulse={running} />
                  {editing === session.session_id ? (
                    <form
                      className="flex min-w-0 flex-1 items-center gap-[4px]"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const next = title.trim();
                        if (next) props.onRename(session.session_id, next);
                        setEditing(undefined);
                      }}
                    >
                      <input
                        aria-label="会话标题"
                        autoFocus
                        value={title}
                        onChange={(event) => setTitle(event.target.value)}
                        className="min-w-0 flex-1 rounded-sm border border-accent bg-surface-1 px-[4px] text-[12.5px] outline-none"
                      />
                      <button aria-label="保存名称" className="text-status-success">
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        aria-label="取消改名"
                        onClick={() => setEditing(undefined)}
                        className="text-text-tertiary"
                      >
                        <X size={14} />
                      </button>
                    </form>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => props.onSelect(session.session_id)}
                        aria-current={active ? 'true' : undefined}
                        title={`${session.title} · ${session.message_count} 条消息${running ? ' · 运行中' : ''}`}
                        className="min-w-0 flex-1 truncate text-left text-[12.5px] font-medium text-text-primary"
                      >
                        {session.title}
                      </button>
                      <span className="flex-none font-mono text-[10px] text-text-tertiary group-hover:invisible">
                        {rowTime(session.updated_at)}
                      </span>
                      <span className="absolute right-[6px] top-1/2 hidden -translate-y-1/2 items-center gap-[3px] rounded-[7px] border border-border-strong bg-surface-3 p-[2px] group-hover:flex group-focus-within:flex">
                        <button
                          type="button"
                          aria-label={`重命名 ${session.title}`}
                          title="改名"
                          onClick={() => {
                            setEditing(session.session_id);
                            setTitle(session.title);
                          }}
                          className="rounded-[5px] px-[6px] py-[2px] text-[10.5px] text-text-tertiary hover:bg-surface-1 hover:text-accent"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          type="button"
                          aria-label={`删除 ${session.title}`}
                          title="删除"
                          onClick={() => props.onDelete(session.session_id)}
                          className="rounded-[5px] px-[6px] py-[2px] text-[10.5px] text-text-tertiary hover:bg-surface-1 hover:text-status-error"
                        >
                          <Trash2 size={12} />
                        </button>
                      </span>
                    </>
                  )}
                </div>
              );
            })}
          </section>
        ))}
        {!props.loading && filtered.length === 0 && (
          <p className="px-[8px] py-[24px] text-center text-caption text-text-tertiary">
            没有匹配的会话
          </p>
        )}
      </div>

      <div className="border-t border-border-subtle p-[8px]">
        <button
          type="button"
          onClick={props.onOpenSkills}
          aria-current={props.skillsActive ? 'page' : undefined}
          className={`relative ${bottomRow} ${props.skillsActive ? 'edge-marker bg-surface-3 text-accent' : ''}`}
        >
          <Grid2X2 size={15} />
          技能·连接器管理
        </button>
        <button type="button" onClick={props.onToggleTheme} className={bottomRow}>
          {props.theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}主题：
          {props.theme === 'dark' ? '深空' : '极昼'}
        </button>
        <div className="mt-[4px] flex items-center gap-[10px] border-t border-border-subtle px-[8px] pb-[2px] pt-[8px]">
          <Avatar name={operatorName} size={28} labelled={false} />
          <span className="flex-1 truncate text-caption font-medium text-text-primary">
            {operatorName}
          </span>
          <button
            type="button"
            aria-label="设置"
            title="设置"
            onClick={props.onOpenSettings}
            className="grid h-[28px] w-[28px] flex-none place-items-center rounded-[7px] text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-accent"
          >
            <Settings size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}
