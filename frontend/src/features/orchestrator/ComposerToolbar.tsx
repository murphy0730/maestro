import { useEffect, useRef, useState } from 'react';
import {
  CalendarCog,
  Check,
  ChevronDown,
  GitBranch,
  Paperclip,
  Search,
  ShieldCheck,
  Square,
  WandSparkles,
  Zap,
} from 'lucide-react';
import type { ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { Button } from '@/components/ui/Button';
import { SendIcon } from '@/components/ui/Icon';
import { Popover } from '@/components/ui/Popover';
import { SkillMenu } from './skills/SkillMenu';

type IconType = typeof WandSparkles;
type OpenMenu = 'route' | 'mode' | 'skill' | null;

const ROUTE_OPTIONS: {
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

const MODE_OPTIONS: {
  id: ComposerMode;
  label: string;
  desc: string;
  icon: IconType;
  tint: string;
}[] = [
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

interface ComposerToolbarProps {
  isStreaming: boolean;
  mode: ComposerMode;
  onClearSkills: () => void;
  onImportSkill: () => void;
  onModeChange: (mode: ComposerMode) => void;
  onRouteChange: (route: ComposerRoute) => void;
  onStop?: () => void;
  onSubmit: () => void;
  onToggleSkill: (skill: SkillMeta) => void;
  route: ComposerRoute;
  selectedSkills: SkillMeta[];
  skills: SkillMeta[];
}

export function ComposerToolbar({
  isStreaming,
  mode,
  onClearSkills,
  onImportSkill,
  onModeChange,
  onRouteChange,
  onStop,
  onSubmit,
  onToggleSkill,
  route,
  selectedSkills,
  skills,
}: ComposerToolbarProps) {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const currentRoute = ROUTE_OPTIONS.find((option) => option.id === route) ?? ROUTE_OPTIONS[0];
  const currentMode = MODE_OPTIONS.find((option) => option.id === mode) ?? MODE_OPTIONS[0];
  const CurrentModeIcon = currentMode.icon;

  useEffect(() => {
    if (!openMenu) return;
    const onPointerDown = (event: MouseEvent) => {
      if (toolbarRef.current && !toolbarRef.current.contains(event.target as Node))
        setOpenMenu(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openMenu]);

  const chip = (active: boolean) =>
    `inline-flex h-[26px] cursor-pointer items-center gap-[6px] rounded-sm border px-[9px] font-sans text-caption font-medium text-text-secondary transition-colors duration-fast ease-out ${
      active
        ? 'border-accent-border bg-accent-bg'
        : 'border-border-default bg-surface-2 hover:bg-surface-3'
    }`;
  const modeChip = (active: boolean) =>
    mode === 'auto'
      ? 'inline-flex h-[26px] cursor-pointer items-center gap-[6px] rounded-sm border border-auth-confirm-border bg-auth-confirm-bg px-[9px] font-sans text-caption font-medium text-auth-confirm transition-colors duration-fast ease-out'
      : chip(active);

  return (
    <div ref={toolbarRef} className="flex items-center gap-2 px-[10px] py-2">
      <button
        title="添加文件"
        aria-label="添加文件"
        className="grid h-[30px] w-[30px] flex-none cursor-pointer place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary"
      >
        <Paperclip size={16} />
      </button>
      <span aria-hidden="true" className="h-[18px] w-px flex-none bg-border-default" />
      <div className="relative">
        <button
          onClick={() => setOpenMenu((current) => (current === 'route' ? null : 'route'))}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'route'}
          className={chip(openMenu === 'route')}
        >
          <span className={`h-[7px] w-[7px] rounded-full ${currentRoute.dot}`} />
          <span className="text-text-primary">{currentRoute.label}</span>
          <ChevronDown size={13} className="text-text-tertiary" />
        </button>
        {openMenu === 'route' && (
          <Popover role="menu" className="absolute bottom-full left-0 mb-2 w-[212px] px-1">
            {ROUTE_OPTIONS.map((option) => {
              const Icon = option.icon;
              const selected = option.id === route;
              return (
                <button
                  key={option.id}
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => {
                    onRouteChange(option.id);
                    setOpenMenu(null);
                  }}
                  className={`flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out ${
                    selected ? 'bg-accent-bg' : 'hover:bg-border-subtle'
                  }`}
                >
                  <span className={`h-[7px] w-[7px] flex-none rounded-full ${option.dot}`} />
                  <Icon size={14} className="flex-none text-text-secondary" />
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="text-body-sm font-semibold text-text-primary">
                      {option.label}
                    </span>
                    <span className="text-[11px] text-text-tertiary">{option.desc}</span>
                  </span>
                  {selected && <Check size={14} className="flex-none text-accent" />}
                </button>
              );
            })}
          </Popover>
        )}
      </div>
      <div className="relative">
        <button
          onClick={() => setOpenMenu((current) => (current === 'mode' ? null : 'mode'))}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'mode'}
          className={modeChip(openMenu === 'mode')}
        >
          <CurrentModeIcon size={13} className={mode === 'auto' ? '' : currentMode.tint} />
          <span className={mode === 'auto' ? '' : 'text-text-primary'}>{currentMode.label}</span>
          <ChevronDown size={13} className="opacity-60" />
        </button>
        {openMenu === 'mode' && (
          <Popover role="menu" className="absolute bottom-full left-0 mb-2 w-[224px] px-1">
            {MODE_OPTIONS.map((option) => {
              const Icon = option.icon;
              const selected = option.id === mode;
              return (
                <button
                  key={option.id}
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => {
                    onModeChange(option.id);
                    setOpenMenu(null);
                  }}
                  className={`flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out ${
                    selected ? 'bg-accent-bg' : 'hover:bg-border-subtle'
                  }`}
                >
                  <Icon size={14} className={`flex-none ${option.tint}`} />
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="text-body-sm font-semibold text-text-primary">
                      {option.label}
                    </span>
                    <span className="text-[11px] text-text-tertiary">{option.desc}</span>
                  </span>
                  {selected && <Check size={14} className="flex-none text-accent" />}
                </button>
              );
            })}
          </Popover>
        )}
      </div>
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
          onClick={onSubmit}
          title="发送消息"
          aria-label="发送消息"
          className="grid h-[30px] w-[30px] flex-none cursor-pointer place-items-center rounded-sm bg-blue-solid text-on-solid shadow-elev-1 transition-colors duration-fast ease-out hover:bg-blue-solid-hover"
        >
          <SendIcon size={15} />
        </button>
      )}
    </div>
  );
}
