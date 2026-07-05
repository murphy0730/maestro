import { useState } from 'react';
import { Sparkles, Check, Search } from 'lucide-react';
import type { SkillMeta } from '@/types/api';

interface SkillMenuProps {
  skills: SkillMeta[];
  skill: SkillMeta | null;
  onSkillChange: (s: SkillMeta | null) => void;
  onImportSkill: () => void;
  open: boolean;
  onToggle: () => void;
}

export function SkillMenu({ skills, skill, onSkillChange, onImportSkill, open, onToggle }: SkillMenuProps) {
  const [q, setQ] = useState('');
  const visible = skills.filter((s) => s.user_invocable !== false);
  const filtered = visible.filter((s) =>
    [s.name, s.display_name, s.description].join(' ').toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        className={`flex items-center gap-1 rounded-md border px-2 py-1 text-body-sm ${
          skill ? 'border-accent-border bg-accent-bg text-accent-fg' : 'border-border-default hover:bg-border-subtle'
        }`}
      >
        <Sparkles size={14} className="text-accent" />
        {skill?.display_name ?? '技能'}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-[260px] rounded-md border border-border-default bg-surface-1 shadow-popover">
          <div className="flex items-center gap-1 border-b border-border-default px-2 py-1">
            <Search size={12} className="text-text-tertiary" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索技能"
              className="w-full bg-transparent text-body-sm placeholder:text-text-tertiary focus:outline-none"
            />
          </div>
          <div className="max-h-[280px] overflow-auto py-1">
            <button
              onClick={() => onSkillChange(null)}
              className="flex w-full items-center justify-between px-2 py-1 hover:bg-border-subtle"
            >
              <span className="text-body-sm text-text-tertiary">不使用技能</span>
              {!skill && <Check size={14} className="text-accent" />}
            </button>
            {filtered.map((s) => (
              <button
                key={s.name}
                onClick={() => onSkillChange(s)}
                className="flex w-full items-start justify-between px-2 py-1 hover:bg-border-subtle"
              >
                <span className="flex flex-col items-start">
                  <span className="text-body-sm font-semibold">{s.display_name ?? s.name}</span>
                  <span className="line-clamp-1 text-[11px] text-text-tertiary">{s.description}</span>
                </span>
                {skill?.name === s.name && <Check size={14} className="text-accent" />}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-2 py-2 text-[11px] text-text-tertiary">暂无技能，点击下方导入</div>
            )}
          </div>
          <div className="border-t border-border-default px-2 py-1">
            <button onClick={onImportSkill} className="text-body-sm text-accent hover:underline">
              导入技能…
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
