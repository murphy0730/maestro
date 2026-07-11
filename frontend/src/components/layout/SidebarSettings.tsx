import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Cable,
  Moon,
  Palette,
  Settings,
  Sparkles,
  Sun,
  UserRoundCog,
} from 'lucide-react';
import type { DefaultEngine, Theme } from '@/stores';
import { Popover, PopoverItem, PopoverLabel } from '@/components/ui/Popover';

const SettingsModal = lazy(async () => ({
  default: (await import('@/features/orchestrator/settings/SettingsModal')).SettingsModal,
}));
const PersonalizationModal = lazy(async () => ({
  default: (await import('@/features/orchestrator/settings/PersonalizationModal'))
    .PersonalizationModal,
}));

const ENGINE_OPTIONS: { value: DefaultEngine; label: string; dot: string }[] = [
  { value: 'auto', label: '自动', dot: 'bg-accent' },
  { value: 'planning', label: '排产', dot: 'bg-planning' },
  { value: 'scheduling', label: '调度', dot: 'bg-scheduling' },
  { value: 'query', label: '查询', dot: 'bg-query' },
];

interface SidebarSettingsProps {
  defaultEngine: DefaultEngine;
  initial?: string;
  onSetDefaultEngine: (engine: DefaultEngine) => void;
  onSetTheme: (theme: Theme) => void;
  role: string;
  theme: Theme;
  user: string;
  onOpenSkills?: () => void;
  onOpenConnectors?: () => void;
}

export function SidebarSettings({
  defaultEngine,
  initial,
  onSetDefaultEngine,
  onSetTheme,
  role,
  theme,
  user,
  onOpenSkills,
  onOpenConnectors,
}: SidebarSettingsProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsView, setSettingsView] = useState<'root' | 'engine'>('root');
  const [modelOpen, setModelOpen] = useState(false);
  const [personalizationOpen, setPersonalizationOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!settingsOpen) return;
    const onClick = (event: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(event.target as Node)) {
        setSettingsOpen(false);
        setSettingsView('root');
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [settingsOpen]);

  return (
    <>
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
              setSettingsOpen((value) => !value);
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
                        onClick={(event) => {
                          event.stopPropagation();
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
                        onClick={(event) => {
                          event.stopPropagation();
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
                  <div className="my-1 border-t border-border-subtle" />
                  <PopoverItem icon={<Sparkles size={15} />} onClick={() => { setSettingsOpen(false); onOpenSkills?.(); }}>
                    技能
                  </PopoverItem>
                  <PopoverItem icon={<Cable size={15} />} onClick={() => { setSettingsOpen(false); onOpenConnectors?.(); }}>
                    连接器
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
                  {ENGINE_OPTIONS.map(({ value, label, dot }) => (
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
      <Suspense fallback={null}>
        {modelOpen && <SettingsModal open onClose={() => setModelOpen(false)} />}
        {personalizationOpen && (
          <PersonalizationModal open onClose={() => setPersonalizationOpen(false)} />
        )}
      </Suspense>
    </>
  );
}
