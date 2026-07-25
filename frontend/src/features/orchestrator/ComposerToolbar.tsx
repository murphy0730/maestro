import { FileText, LayoutGrid, Paperclip, Sparkles, Square, X } from 'lucide-react';
import type { SkillMeta } from '@/types';
import { SendIcon } from '@/components/ui/Icon';
import type { RunMode } from '@/stores/uiPreferencesStore';

interface Props {
  disabled?: boolean;
  submitDisabled?: boolean;
  onAddAttachment: () => void;
  attachments: File[];
  onRemoveAttachment: (name: string) => void;
  isStreaming: boolean;
  skillMenuOpen: boolean;
  onToggleSkillMenu: () => void;
  onStop?: () => void;
  onSubmit: () => void;
  onToggleSkill: (skill: SkillMeta) => void;
  selectedSkills: SkillMeta[];
  mode: RunMode;
  onModeChange: (mode: RunMode) => void;
}

/** 设计稿 .cico：输入条上的 30px 图标键。 */
const iconKey =
  'grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-text-tertiary transition-colors duration-fast ease-out hover:bg-surface-3 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50';
/** 设计稿 .chip：已挂载技能 / 附件。 */
const chip =
  'inline-flex items-center gap-[6px] rounded-pill border border-border-subtle bg-surface-2 px-[10px] py-[3px] text-[11px] text-text-secondary';

export function ComposerToolbar({
  disabled,
  submitDisabled,
  onAddAttachment,
  attachments,
  onRemoveAttachment,
  isStreaming,
  skillMenuOpen,
  onToggleSkillMenu,
  onStop,
  onSubmit,
  onToggleSkill,
  selectedSkills,
  mode,
  onModeChange,
}: Props) {
  return (
    <div className="mt-[10px] flex flex-wrap items-center gap-[8px]">
      <button
        type="button"
        disabled={disabled}
        onClick={onAddAttachment}
        aria-label="添加文件"
        title="附件"
        className={iconKey}
      >
        <Paperclip size={16} />
      </button>

      <button
        type="button"
        disabled={disabled}
        onClick={onToggleSkillMenu}
        aria-haspopup="menu"
        aria-expanded={skillMenuOpen}
        aria-label={selectedSkills.length > 0 ? `技能，已选 ${selectedSkills.length} 项` : '技能'}
        title="技能"
        className={`${iconKey} ${skillMenuOpen || selectedSkills.length > 0 ? '!text-accent' : ''}`}
      >
        <LayoutGrid size={16} />
      </button>

      <select
        aria-label="运行模式"
        title="模式"
        disabled={disabled}
        value={mode}
        onChange={(event) => onModeChange(event.target.value as RunMode)}
        data-mode={mode}
        className="mode-select h-[26px] rounded-md border px-[8px] text-[11px]"
      >
        <option value="auto">自动</option>
        <option value="planning">排产</option>
        <option value="scheduling">调度</option>
        <option value="query">查询</option>
      </select>

      {selectedSkills.map((skill) => (
        <span key={skill.name} className={`${chip} border-accent-border bg-accent-bg text-accent`}>
          <Sparkles size={11} />
          {skill.display_name ?? skill.name}
          <button
            type="button"
            aria-label={`移除技能 ${skill.display_name ?? skill.name}`}
            title="移除技能"
            onClick={() => onToggleSkill(skill)}
            className="text-text-tertiary transition-colors hover:text-status-error"
          >
            <X size={11} />
          </button>
        </span>
      ))}

      {attachments.map((file) => (
        <span key={file.name} className={chip}>
          <FileText size={11} />
          {file.name}
          <button
            type="button"
            aria-label={`移除附件 ${file.name}`}
            title="移除附件"
            onClick={() => onRemoveAttachment(file.name)}
            className="text-text-tertiary transition-colors hover:text-status-error"
          >
            <X size={11} />
          </button>
        </span>
      ))}

      <span className="flex-1" />
      <span aria-hidden="true" className="font-mono text-[10.5px] text-text-tertiary">
        ENTER ↵
      </span>

      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          aria-label="停止运行"
          title="停止"
          className="stop-key grid h-[34px] w-[34px] flex-none place-items-center rounded-md transition duration-fast ease-out"
        >
          <Square size={13} fill="currentColor" />
        </button>
      ) : (
        <button
          type="button"
          disabled={submitDisabled}
          onClick={onSubmit}
          aria-label="发送消息"
          title="发送"
          className="send-key grid h-[34px] w-[34px] flex-none place-items-center rounded-md transition duration-fast ease-out disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          <SendIcon size={15} />
        </button>
      )}
    </div>
  );
}
