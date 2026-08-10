import { useEffect, useRef, useState } from 'react';
import type { SkillMeta } from '@/types';
import type { RunMode } from '@/stores/uiPreferencesStore';
import { ComposerToolbar } from './ComposerToolbar';
import { SkillMenu } from './skills/SkillMenu';

interface ComposerProps {
  onSend: (text: string, attachments: File[]) => void | Promise<void>;
  disabled?: boolean;
  isStreaming?: boolean;
  onStop?: () => void;
  skills: SkillMeta[];
  selectedSkills: SkillMeta[];
  onToggleSkill: (skill: SkillMeta) => void;
  onClearSkills: () => void;
  onImportSkill: () => void;
  onTrustSkill?: (skill: SkillMeta) => void;
  mode?: RunMode;
  onModeChange?: (mode: RunMode) => void;
}

const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

/**
 * Composer — 设计稿 A/B/F 的 `.comp-box`：640px 玻璃输入条，聚焦时青色描边 + 辉光。
 * 工具栏单行承载附件、技能、模式、已挂载项与发送/停止键。
 */
export function Composer({
  onSend,
  disabled = false,
  isStreaming = false,
  onStop,
  skills,
  selectedSkills,
  onToggleSkill,
  onClearSkills,
  onImportSkill,
  onTrustSkill,
  mode = 'auto',
  onModeChange = () => undefined,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const modeUnsupported = mode !== 'auto' && mode !== 'scheduling';

  // 技能面板：Esc 或点击输入条外部关闭。
  useEffect(() => {
    if (!skillMenuOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setSkillMenuOpen(false);
    const onPointerDown = (event: MouseEvent) => {
      if (!dockRef.current?.contains(event.target as Node)) setSkillMenuOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [skillMenuOpen]);

  const clearSubmitted = () => {
    setDraft('');
    setAttachments([]);
    onClearSkills();
  };
  const submit = () => {
    if (isStreaming || submitting || disabled || modeUnsupported || !draft.trim()) return;
    const result = onSend(draft.trim(), attachments);
    if (result instanceof Promise) {
      setSubmitting(true);
      void result
        .then(clearSubmitted)
        .catch(() => undefined)
        .finally(() => setSubmitting(false));
    } else clearSubmitted();
  };
  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const acceptable = Array.from(files).filter((file) => file.size <= MAX_ATTACHMENT_BYTES);
    if (acceptable.length !== files.length) setAttachmentError('附件不能超过 10 MB');
    else setAttachmentError('');
    setAttachments((current) => {
      const merged = [
        ...current.filter((item) => !acceptable.some((file) => file.name === item.name)),
        ...acceptable,
      ];
      if (merged.length > 10) setAttachmentError('最多添加 10 个附件');
      return merged.slice(0, 10);
    });
  };

  return (
    <div className="flex-none px-[26px] pb-[18px] pt-[14px]">
      <div className="relative mx-auto max-w-[640px]" ref={dockRef}>
        <SkillMenu
          open={skillMenuOpen}
          skills={skills}
          selected={selectedSkills}
          onToggleSkill={onToggleSkill}
          onClear={onClearSkills}
          onImportSkill={onImportSkill}
          onTrustSkill={onTrustSkill}
        />
        <div className="material-dock glow-ring rounded-[14px] border border-border-strong px-[14px] pb-[10px] pt-[12px] transition duration-normal ease-out">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <textarea
            disabled={disabled || submitting}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={
              submitting
                ? '正在连接或上传…'
                : disabled
                  ? '正在加载会话…'
                  : '描述要完成的制造任务，或附加资料…'
            }
            className="block max-h-[120px] min-h-[22px] w-full resize-none border-none bg-transparent font-sans text-[13.5px] leading-[1.6] text-text-primary outline-none placeholder:text-text-tertiary"
          />
          <ComposerToolbar
            disabled={disabled || submitting}
            submitDisabled={disabled || submitting || modeUnsupported || !draft.trim()}
            isStreaming={isStreaming}
            attachments={attachments}
            onRemoveAttachment={(name) =>
              setAttachments((items) => items.filter((item) => item.name !== name))
            }
            skillMenuOpen={skillMenuOpen}
            onToggleSkillMenu={() => setSkillMenuOpen((open) => !open)}
            onStop={onStop}
            onSubmit={submit}
            onAddAttachment={() => fileInputRef.current?.click()}
            onToggleSkill={onToggleSkill}
            selectedSkills={selectedSkills}
            mode={mode}
            onModeChange={onModeChange}
          />
        </div>
        {attachmentError && (
          <p role="alert" className="mt-[6px] text-caption text-status-error">
            {attachmentError}
          </p>
        )}
        {modeUnsupported && (
          <p role="alert" className="mt-[6px] text-caption text-status-warning">
            后端暂不支持该模式；当前仅支持“自动”与“调度”，请切换后发送。
          </p>
        )}
      </div>
    </div>
  );
}
