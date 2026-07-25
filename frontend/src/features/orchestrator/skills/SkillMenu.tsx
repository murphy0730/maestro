import { useState } from 'react';
import { Check } from 'lucide-react';
import type { SkillMeta } from '@/types/api';
import { Badge } from '@/components/ui/Badge';

interface SkillMenuProps {
  skills: SkillMeta[];
  selected: SkillMeta[];
  onToggleSkill: (skill: SkillMeta) => void;
  onClear: () => void;
  onImportSkill: () => void;
  onTrustSkill?: (skill: SkillMeta) => void;
  open: boolean;
}

/**
 * SkillMenu — 设计稿 F：浮在输入条上方的 400px 技能选择面板。
 * 勾选框直接挂载到本次 run；信任状态用真实的 `trust.valid` 呈现，未信任项就地可信任。
 * 触发按钮在 ComposerToolbar 里，面板由 Composer 定位在整个输入条之上。
 */
export function SkillMenu({
  skills,
  selected,
  onToggleSkill,
  onClear,
  onImportSkill,
  onTrustSkill,
  open,
}: SkillMenuProps) {
  const [query, setQuery] = useState('');
  const visible = skills.filter((skill) => skill.user_invocable !== false);
  const filtered = visible.filter((skill) =>
    [skill.name, skill.display_name, skill.summary_zh, skill.description_zh, skill.description]
      .join(' ')
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const isSelected = (skill: SkillMeta) => selected.some((item) => item.name === skill.name);

  if (!open) return null;
  return (
    <div
      role="menu"
      aria-label="选择技能"
      className="material-popover absolute bottom-full left-0 z-30 mb-[14px] w-[400px] max-w-full overflow-hidden rounded-[14px] border border-border-strong shadow-popover"
    >
      <div className="flex items-center gap-[10px] border-b border-border-subtle px-[14px] py-[12px]">
        <span className="hud-label text-text-tertiary">选择技能 · Skills</span>
        <span className="flex-1" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索…"
          aria-label="搜索技能"
          className="w-[132px] rounded-md border border-border-subtle bg-surface-2 px-[10px] py-[5px] text-[11.5px] text-text-primary outline-none transition-colors focus:border-accent placeholder:text-text-tertiary"
        />
      </div>

      <div className="max-h-[300px] overflow-y-auto">
        {filtered.map((skill) => {
          const checked = isSelected(skill);
          const trusted = skill.trust?.valid ?? false;
          return (
            <div
              key={skill.name}
              role="menuitemcheckbox"
              aria-checked={checked}
              tabIndex={0}
              onClick={() => onToggleSkill(skill)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onToggleSkill(skill);
                }
              }}
              className="flex cursor-pointer items-start gap-[11px] px-[14px] py-[11px] transition-colors duration-fast hover:bg-surface-3"
            >
              <span
                aria-hidden="true"
                className={`mt-[2px] grid h-[16px] w-[16px] flex-none place-items-center rounded-[5px] border-[1.5px] transition-all duration-fast ${
                  checked
                    ? 'border-accent bg-accent text-text-on-color shadow-glow-accent'
                    : 'border-text-tertiary text-transparent'
                }`}
              >
                <Check size={10} strokeWidth={3} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-[8px] text-body-sm font-medium text-text-primary">
                  <span className="truncate">{skill.display_name ?? skill.name}</span>
                  <Badge tone={trusted ? 'success' : 'warning'} className="flex-none !text-[9px]">
                    {trusted ? '已信任' : '未信任'}
                  </Badge>
                </span>
                <span className="mt-[2px] block truncate text-[11.5px] text-text-secondary">
                  {skill.summary_zh ?? skill.description}
                </span>
              </span>
              {!trusted && skill.scripts?.length ? (
                <button
                  type="button"
                  title="信任当前版本脚本"
                  aria-label={`信任 ${skill.display_name ?? skill.name}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onTrustSkill?.(skill);
                  }}
                  className="flex-none rounded-sm border border-border-strong px-[9px] py-[2px] text-[10.5px] text-text-primary transition-colors hover:border-accent hover:text-accent"
                >
                  信任
                </button>
              ) : null}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <p className="px-[14px] py-[16px] text-[11.5px] text-text-tertiary">
            暂无匹配的技能，可从下方导入
          </p>
        )}
      </div>

      <div className="flex items-center gap-[10px] border-t border-border-subtle px-[14px] py-[10px] text-[11.5px] text-text-tertiary">
        <span>
          已选 <b className="font-medium text-accent">{selected.length}</b> 项
        </span>
        <button
          type="button"
          aria-label="清空已选"
          onClick={onClear}
          disabled={selected.length === 0}
          className="text-accent transition-opacity hover:underline disabled:cursor-not-allowed disabled:opacity-40"
        >
          清空
        </button>
        <span className="flex-1" />
        <button
          type="button"
          aria-label="导入技能"
          onClick={onImportSkill}
          className="text-accent transition-colors hover:underline"
        >
          ＋ 导入技能
        </button>
      </div>
    </div>
  );
}
