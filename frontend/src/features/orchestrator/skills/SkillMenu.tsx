import { useState } from 'react';
import { Sparkles, Check, Search, ChevronDown, Import, Ban } from 'lucide-react';
import type { SkillMeta } from '@/types/api';

interface SkillMenuProps {
  skills: SkillMeta[];
  skill: SkillMeta | null;
  onSkillChange: (s: SkillMeta | null) => void;
  onImportSkill: () => void;
  open: boolean;
  onToggle: () => void;
}

export function SkillMenu({
  skills,
  skill,
  onSkillChange,
  onImportSkill,
  open,
  onToggle,
}: SkillMenuProps) {
  const [q, setQ] = useState('');
  const visible = skills.filter((s) => s.user_invocable !== false);
  const filtered = visible.filter((s) =>
    [s.name, s.display_name, s.description].join(' ').toLowerCase().includes(q.toLowerCase()),
  );

  // Same chip shape as the route/mode selectors so the toolbar reads as one system.
  const active = open || !!skill;
  const chip = `inline-flex h-8 cursor-pointer items-center gap-[6px] rounded-md border px-[9px] font-sans text-caption font-semibold text-text-secondary transition-colors duration-fast ease-out ${
    active ? 'border-accent-border bg-accent-bg' : 'border-border-default hover:bg-border-subtle'
  }`;

  // One dropdown row — mirrors the route/mode option rows.
  const row =
    'flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={open}
        className={chip}
      >
        <Sparkles size={13} className="text-accent" />
        <span className="text-text-primary">{skill?.display_name ?? '技能'}</span>
        <ChevronDown size={13} className="text-text-tertiary" />
      </button>

      {open && (
        <div className="material-popover absolute bottom-full left-0 mb-2 w-[264px] rounded-md border border-border-default shadow-popover">
          <div className="flex items-center gap-[6px] border-b border-border-default px-[10px] py-[7px]">
            <Search size={13} className="flex-none text-text-tertiary" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索技能"
              className="w-full bg-transparent text-body-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
            />
          </div>

          <div className="max-h-[280px] overflow-auto px-1 py-1">
            <button
              role="menuitemradio"
              aria-checked={!skill}
              onClick={() => onSkillChange(null)}
              className={`${row} ${!skill ? 'bg-accent-bg' : 'hover:bg-border-subtle'}`}
            >
              <Ban size={14} className="flex-none text-text-tertiary" />
              <span className="min-w-0 flex-1 text-body-sm text-text-secondary">不使用技能</span>
              {!skill && <Check size={14} className="flex-none text-accent" />}
            </button>

            {filtered.map((s) => {
              const selected = skill?.name === s.name;
              return (
                <button
                  key={s.name}
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => onSkillChange(s)}
                  className={`${row} ${selected ? 'bg-accent-bg' : 'hover:bg-border-subtle'}`}
                >
                  <Sparkles size={14} className="flex-none text-text-secondary" />
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="truncate text-body-sm font-semibold text-text-primary">
                      {s.display_name ?? s.name}
                    </span>
                    <span className="truncate text-[11px] text-text-tertiary">{s.description}</span>
                  </span>
                  {selected && <Check size={14} className="flex-none text-accent" />}
                </button>
              );
            })}

            {filtered.length === 0 && (
              <div className="px-2 py-2 text-[11px] text-text-tertiary">暂无技能，点击下方导入</div>
            )}
          </div>

          <div className="border-t border-border-default px-1 py-1">
            <button
              onClick={onImportSkill}
              className={`${row} text-text-secondary hover:bg-border-subtle`}
            >
              <Import size={14} className="flex-none text-text-tertiary" />
              <span className="text-body-sm font-medium">导入技能</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
