import { useEffect, useRef, useState } from 'react';
import {
  Paperclip,
  Zap,
  ShieldCheck,
  CalendarCog,
  GitBranch,
  Search,
  Square,
  WandSparkles,
  ChevronDown,
  Check,
  Sparkles,
  X,
} from 'lucide-react';
import type { ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { Button } from '@/components/ui/Button';
import { SendIcon } from '@/components/ui/Icon';
import { Popover } from '@/components/ui/Popover';
import { SkillMenu } from './skills/SkillMenu';

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
  /** Registered skill packages (drives the skills chip popover). */
  skills: SkillMeta[];
  /** Currently selected skills (multi-select). */
  selectedSkills: SkillMeta[];
  onToggleSkill: (s: SkillMeta) => void;
  onClearSkills: () => void;
  /** Open the skill import modal (owned by Workspace). */
  onImportSkill: () => void;
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

/**
 * Full access (`auto`) bypasses the ActionGate's `requires_confirmation` step,
 * so it is the most powerful click in the app. Its chip is tinted amber rather
 * than neutral: a risky option should look risky.
 */
const MODE_OPTS: { id: ComposerMode; label: string; desc: string; icon: IconType; tint: string }[] =
  [
    {
      id: 'plan',
      label: '默认模式',
      desc: '写操作停在 ActionGate，等你确认',
      icon: ShieldCheck,
      tint: 'text-text-secondary',
    },
    {
      id: 'auto',
      label: '完全访问模式',
      desc: 'Agent 可直接读写文件',
      icon: Zap,
      tint: 'text-auth-confirm',
    },
  ];

type OpenMenu = 'route' | 'mode' | 'skill' | null;

export function Composer({
  onSend,
  route,
  mode,
  onRouteChange,
  onModeChange,
  isStreaming = false,
  onStop,
  skills,
  selectedSkills,
  onToggleSkill,
  onClearSkills,
  onImportSkill,
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
    `inline-flex h-[26px] cursor-pointer items-center gap-[6px] rounded-sm border px-[9px] font-sans text-caption font-medium text-text-secondary transition-colors duration-fast ease-out ${
      active
        ? 'border-accent-border bg-accent-bg'
        : 'border-border-default bg-surface-2 hover:bg-surface-3'
    }`;

  /** Full-access mode keeps its amber tint even when its menu is closed. */
  const modeChip = (active: boolean) =>
    mode === 'auto'
      ? `inline-flex h-[26px] cursor-pointer items-center gap-[6px] rounded-sm border border-auth-confirm-border bg-auth-confirm-bg px-[9px] font-sans text-caption font-medium text-auth-confirm transition-colors duration-fast ease-out`
      : chip(active);

  return (
    <div className="flex-none px-[30px] pb-[18px] pt-2">
      <div className="pointer-events-auto mx-auto max-w-[760px]">
        <div
          className={`material-dock rounded-lg border transition-colors duration-fast ${
            slash
              ? 'border-accent-border shadow-glow-accent'
              : 'border-border-default shadow-elev-2'
          }`}
        >
          {selectedSkills.length > 0 && (
            <div className="flex flex-wrap items-center gap-[6px] px-[12px] pt-[10px]">
              {selectedSkills.map((s) => (
                <span
                  key={s.name}
                  className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-accent-border bg-accent-bg px-[8px] text-caption font-medium text-text-primary"
                >
                  <Sparkles size={12} className="text-accent" />
                  {s.display_name ?? s.name}
                  <button
                    type="button"
                    title="移除技能"
                    onClick={() => onToggleSkill(s)}
                    className="grid h-[16px] w-[16px] place-items-center rounded-sm text-text-tertiary hover:bg-border-subtle hover:text-text-secondary"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
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
            {/* Attachment is an input source, not a send modifier — it sits
                furthest left, fenced off from the route/mode/skill chips. */}
            <button
              title="添加文件"
              aria-label="添加文件"
              className="grid h-[30px] w-[30px] flex-none cursor-pointer place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary"
            >
              <Paperclip size={16} />
            </button>
            <span aria-hidden="true" className="h-[18px] w-px flex-none bg-border-default" />

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
                className={modeChip(openMenu === 'mode')}
              >
                <CurModeIcon size={13} className={mode === 'auto' ? '' : curMode.tint} />
                <span className={mode === 'auto' ? '' : 'text-text-primary'}>{curMode.label}</span>
                <ChevronDown size={13} className="opacity-60" />
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

            {/* skill selector — click to open, pick a skill package */}
            <SkillMenu
              skills={skills}
              selected={selectedSkills}
              onToggleSkill={onToggleSkill}
              onClear={onClearSkills}
              onImportSkill={onImportSkill}
              open={openMenu === 'skill'}
              onToggle={() => setOpenMenu(openMenu === 'skill' ? null : 'skill')}
            />

            <span className="flex-1" />
            {/* Send is the terminus: pinned right, the only solid-blue square
                icon button in the app. */}
            {isStreaming ? (
              <Button
                variant="danger"
                onClick={onStop}
                leadingIcon={<Square size={12} fill="currentColor" />}
              >
                停止
              </Button>
            ) : (
              <button
                type="button"
                onClick={submit}
                title="发送消息"
                aria-label="发送消息"
                className="grid h-[30px] w-[30px] flex-none cursor-pointer place-items-center rounded-sm bg-blue-solid text-on-solid shadow-elev-1 transition-colors duration-fast ease-out hover:bg-blue-solid-hover"
              >
                <SendIcon size={15} />
              </button>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-center gap-[7px] text-[11px] text-text-tertiary">
          {mode === 'auto' ? (
            <Zap size={12} className="text-auth-confirm" />
          ) : (
            <ShieldCheck size={12} className="text-text-tertiary" />
          )}
          <span>
            {route === 'auto' ? '引擎自动分类' : `指定 ${curRoute.label}引擎`} ·{' '}
            {mode === 'auto'
              ? '完全访问模式：Agent 可直接写入 MES'
              : '默认模式：写操作需确认后执行'}
          </span>
          <span className="flex-1" />
          <span className="font-mono">Enter 发送 · Shift+Enter 换行</span>
        </div>
      </div>
    </div>
  );
}
