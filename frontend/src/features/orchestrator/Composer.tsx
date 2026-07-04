import { useEffect, useRef, useState } from 'react';
import {
  Paperclip,
  ArrowUp,
  Zap,
  ShieldCheck,
  CalendarCog,
  GitBranch,
  Search,
  WandSparkles,
  ChevronDown,
  Check,
} from 'lucide-react';
import type { ComposerMode, ComposerRoute } from '@/types';
import { Button } from '@/components/ui/Button';
import { Popover } from '@/components/ui/Popover';

/**
 * Composer — the message input. Draft text is local UI state; the route and
 * mode selectors are controlled by props so the parent owns routing intent.
 * Each selector chip opens a popover; clicking an option selects it.
 */
interface ComposerProps {
  onSend: (text: string) => void;
  route: ComposerRoute;
  mode: ComposerMode;
  onRouteChange: (route: ComposerRoute) => void;
  onModeChange: (mode: ComposerMode) => void;
  /** Stream in flight: the send button becomes a stop button. */
  isStreaming?: boolean;
  /** Abort the in-flight stream (wired to useOrchestrator.stop). */
  onStop?: () => void;
}

type IconType = typeof WandSparkles;

const ROUTE_OPTS: {
  id: ComposerRoute;
  label: string;
  desc: string;
  dot: string;
  icon: IconType;
}[] = [
  { id: 'auto', label: '自动', desc: '引擎自动分类', dot: 'bg-accent', icon: WandSparkles },
  { id: 'planning', label: '排产', desc: '指定排产引擎', dot: 'bg-planning', icon: CalendarCog },
  { id: 'scheduling', label: '调度', desc: '指定调度引擎', dot: 'bg-scheduling', icon: GitBranch },
  { id: 'query', label: '查询', desc: '指定查询引擎', dot: 'bg-query', icon: Search },
];

const MODE_OPTS: { id: ComposerMode; label: string; desc: string; icon: IconType; tint: string }[] =
  [
    {
      id: 'plan',
      label: 'Plan mode',
      desc: '写操作需确认后执行',
      icon: ShieldCheck,
      tint: 'text-auth-confirm',
    },
    {
      id: 'auto',
      label: 'Auto mode',
      desc: '自动执行 AUTO 级动作',
      icon: Zap,
      tint: 'text-auth-auto',
    },
  ];

type OpenMenu = 'route' | 'mode' | null;

export function Composer({
  onSend,
  route,
  mode,
  onRouteChange,
  onModeChange,
  isStreaming = false,
  onStop,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);

  const slash = draft.startsWith('/');
  const submit = () => {
    if (isStreaming) return;
    const t = draft.trim();
    if (t) {
      onSend(t);
      setDraft('');
    }
  };
  const curRoute = ROUTE_OPTS.find((r) => r.id === route) ?? ROUTE_OPTS[0];
  const curMode = MODE_OPTS.find((m) => m.id === mode) ?? MODE_OPTS[0];
  const CurModeIcon = curMode.icon;

  // Close any open popover on outside click or Escape.
  useEffect(() => {
    if (!openMenu) return;
    const onDown = (e: MouseEvent) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target as Node)) setOpenMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [openMenu]);

  const chip = (active: boolean) =>
    `inline-flex h-8 cursor-pointer items-center gap-[6px] rounded-md border px-[9px] font-sans text-caption font-semibold text-text-secondary transition-colors duration-fast ease-out ${
      active ? 'border-accent-border bg-accent-bg' : 'border-border-default hover:bg-border-subtle'
    }`;

  return (
    <div className="flex-none px-[30px] pb-[18px] pt-2">
      <div className="pointer-events-auto mx-auto max-w-[760px]">
        <div
          className={`material-dock rounded-xl border transition-colors duration-fast ${
            slash
              ? 'border-accent-border shadow-glow-accent'
              : 'border-border-default shadow-elev-2'
          }`}
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="描述排产 / 调度 / 查询需求，输入 / 调用斜杠命令，或粘贴工单号 WO-…"
            className="block max-h-[120px] w-full resize-none border-none bg-transparent px-[15px] pb-[7px] pt-[13px] font-sans text-body leading-normal text-text-primary outline-none placeholder:text-text-tertiary"
          />
          <div ref={toolbarRef} className="flex items-center gap-2 px-[10px] py-2">
            <button
              title="添加文件"
              className="grid h-8 w-8 flex-none cursor-pointer place-items-center rounded-md border border-border-default text-text-tertiary transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary"
            >
              <Paperclip size={16} />
            </button>

            {/* route selector — click to open, pick one */}
            <div className="relative">
              <button
                onClick={() => setOpenMenu((m) => (m === 'route' ? null : 'route'))}
                aria-haspopup="menu"
                aria-expanded={openMenu === 'route'}
                className={chip(openMenu === 'route')}
              >
                <span className={`h-[7px] w-[7px] rounded-full ${curRoute.dot}`} />
                <span className="text-text-primary">{curRoute.label}</span>
                <ChevronDown size={13} className="text-text-tertiary" />
              </button>
              {openMenu === 'route' && (
                <Popover role="menu" className="absolute bottom-full left-0 mb-2 w-[212px] px-1">
                  {ROUTE_OPTS.map((o) => {
                    const Icon = o.icon;
                    const selected = o.id === route;
                    return (
                      <button
                        key={o.id}
                        role="menuitemradio"
                        aria-checked={selected}
                        onClick={() => {
                          onRouteChange(o.id);
                          setOpenMenu(null);
                        }}
                        className={`flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out ${
                          selected ? 'bg-accent-bg' : 'hover:bg-border-subtle'
                        }`}
                      >
                        <span className={`h-[7px] w-[7px] flex-none rounded-full ${o.dot}`} />
                        <Icon size={14} className="flex-none text-text-secondary" />
                        <span className="flex min-w-0 flex-1 flex-col leading-tight">
                          <span className="text-body-sm font-semibold text-text-primary">
                            {o.label}
                          </span>
                          <span className="text-[11px] text-text-tertiary">{o.desc}</span>
                        </span>
                        {selected && <Check size={14} className="flex-none text-accent" />}
                      </button>
                    );
                  })}
                </Popover>
              )}
            </div>

            {/* mode selector — click to open, pick one */}
            <div className="relative">
              <button
                onClick={() => setOpenMenu((m) => (m === 'mode' ? null : 'mode'))}
                aria-haspopup="menu"
                aria-expanded={openMenu === 'mode'}
                className={chip(openMenu === 'mode')}
              >
                <CurModeIcon size={13} className={curMode.tint} />
                <span className="text-text-primary">{curMode.label}</span>
                <ChevronDown size={13} className="text-text-tertiary" />
              </button>
              {openMenu === 'mode' && (
                <Popover role="menu" className="absolute bottom-full left-0 mb-2 w-[224px] px-1">
                  {MODE_OPTS.map((o) => {
                    const Icon = o.icon;
                    const selected = o.id === mode;
                    return (
                      <button
                        key={o.id}
                        role="menuitemradio"
                        aria-checked={selected}
                        onClick={() => {
                          onModeChange(o.id);
                          setOpenMenu(null);
                        }}
                        className={`flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out ${
                          selected ? 'bg-accent-bg' : 'hover:bg-border-subtle'
                        }`}
                      >
                        <Icon size={14} className={`flex-none ${o.tint}`} />
                        <span className="flex min-w-0 flex-1 flex-col leading-tight">
                          <span className="text-body-sm font-semibold text-text-primary">
                            {o.label}
                          </span>
                          <span className="text-[11px] text-text-tertiary">{o.desc}</span>
                        </span>
                        {selected && <Check size={14} className="flex-none text-accent" />}
                      </button>
                    );
                  })}
                </Popover>
              )}
            </div>

            <span className="flex-1" />
            {isStreaming ? (
              <Button
                variant="danger"
                onClick={onStop}
                leadingIcon={<Square size={12} fill="currentColor" />}
              >
                停止
              </Button>
            ) : (
              <Button variant="primary" onClick={submit} leadingIcon={<ArrowUp size={15} />}>
                发送
              </Button>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-center gap-[7px] text-[11px] text-text-tertiary">
          {mode === 'auto' ? (
            <Zap size={12} className="text-auth-auto" />
          ) : (
            <ShieldCheck size={12} className="text-auth-confirm" />
          )}
          <span>
            {route === 'auto' ? '引擎自动分类' : `指定 ${curRoute.label}引擎`} ·{' '}
            {mode === 'auto' ? 'Auto mode：自动执行 AUTO 级动作' : 'Plan mode：写操作需确认后执行'}
          </span>
          <span className="flex-1" />
          <span className="font-mono">Enter 发送 · Shift+Enter 换行</span>
        </div>
      </div>
    </div>
  );
}
