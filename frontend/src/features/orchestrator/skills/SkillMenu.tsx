import { useState } from 'react';
import { Sparkles, Check, Search, ChevronDown, Import, Ban, ShieldCheck } from 'lucide-react';
import type { SkillMeta } from '@/types/api';

interface SkillMenuProps {
  skills: SkillMeta[];
  selected: SkillMeta[];
  onToggleSkill: (s: SkillMeta) => void;
  onClear: () => void;
  onImportSkill: () => void;
  onTrustSkill?: (skill: SkillMeta) => void;
  open: boolean;
  onToggle: () => void;
}

export function SkillMenu({
  skills,
  selected,
  onToggleSkill,
  onClear,
  onImportSkill,
  onTrustSkill,
  open,
  onToggle,
}: SkillMenuProps) {
  const [q, setQ] = useState('');
  const visible = skills.filter((s) => s.user_invocable !== false);
  const filtered = visible.filter((s) =>
    [s.name, s.display_name, s.summary_zh, s.description_zh, s.description]
      .join(' ')
      .toLowerCase()
      .includes(q.toLowerCase()),
  );
  const isSel = (s: SkillMeta) => selected.some((x) => x.name === s.name);

  // Same chip shape as the rest of the composer controls.
  const active = open || selected.length > 0;
  const chip = `inline-flex h-8 cursor-pointer items-center gap-[6px] rounded-md border px-[9px] font-sans text-caption font-semibold text-text-secondary transition-colors duration-fast ease-out ${
    active ? 'border-accent-border bg-accent-bg' : 'border-border-default hover:bg-border-subtle'
  }`;

  // One compact dropdown row per available Skill.
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
        <span className="text-text-primary">
          {selected.length > 0 ? `技能 · ${selected.length}` : '技能'}
        </span>
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
              type="button"
              onClick={onClear}
              disabled={selected.length === 0}
              className={`${row} ${
                selected.length === 0 ? 'opacity-50' : 'hover:bg-border-subtle'
              }`}
            >
              <Ban size={14} className="flex-none text-text-tertiary" />
              <span className="min-w-0 flex-1 text-body-sm text-text-secondary">清空已选</span>
            </button>

            {filtered.map((s) => {
              const selectedNow = isSel(s);
              return (
                <div
                  key={s.name}
                  role="menuitemcheckbox"
                  aria-checked={selectedNow}
                  onClick={() => onToggleSkill(s)}
                  className={`${row} ${selectedNow ? 'bg-accent-bg' : 'hover:bg-border-subtle'}`}
                >
                  <Sparkles size={14} className="flex-none text-text-secondary" />
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="truncate text-body-sm font-semibold text-text-primary">
                      {s.display_name ?? s.name}
                    </span>
                    <span className="truncate text-[11px] text-text-tertiary">
                      {s.summary_zh ?? s.description}
                    </span>
                  </span>
                  {s.scripts?.length && !s.trust?.valid ? (
                    <button
                      type="button"
                      title="信任当前版本脚本"
                      onClick={(event) => {
                        event.stopPropagation();
                        onTrustSkill?.(s);
                      }}
                      className="rounded-sm border border-status-warning/40 p-1 text-status-warning"
                    >
                      <ShieldCheck size={13} />
                    </button>
                  ) : null}
                  {selectedNow && <Check size={14} className="flex-none text-accent" />}
                </div>
              );
            })}

            {filtered.length === 0 && (
              <div className="px-2 py-2 text-[11px] text-text-tertiary">暂无技能，点击下方导入</div>
            )}
          </div>

          <div className="border-t border-border-default px-1 py-1">
            <button
              type="button"
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
