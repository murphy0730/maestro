import { useRef, useState } from 'react';
import { FileText, ShieldCheck, Sparkles, X, Zap } from 'lucide-react';
import type { ChatAttachment, ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { ComposerToolbar } from './ComposerToolbar';

interface ComposerProps {
  onSend: (text: string, attachments: ChatAttachment[]) => void;
  route: ComposerRoute;
  mode: ComposerMode;
  onRouteChange: (route: ComposerRoute) => void;
  onModeChange: (mode: ComposerMode) => void;
  isStreaming?: boolean;
  onStop?: () => void;
  skills: SkillMeta[];
  selectedSkills: SkillMeta[];
  onToggleSkill: (skill: SkillMeta) => void;
  onClearSkills: () => void;
  onImportSkill: () => void;
  onTrustSkill?: (skill: SkillMeta) => void;
}

const ROUTE_LABELS: Record<ComposerRoute, string> = {
  auto: '自动',
  planning: '排产',
  scheduling: '调度',
  query: '查询',
};

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
  onTrustSkill,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const slash = draft.startsWith('/');
  const routeLabel = ROUTE_LABELS[route];

  const submit = () => {
    if (isStreaming) return;
    const text = draft.trim();
    if (!text) return;
    onSend(text, attachments);
    setDraft('');
    setAttachments([]);
  };

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    setAttachmentError('');
    const next: ChatAttachment[] = [];
    for (const file of Array.from(files)) {
      if (file.size > 1024 * 1024) {
        setAttachmentError(`${file.name} 超过 1 MB，未添加`);
        continue;
      }
      next.push({
        name: file.name,
        content_type: file.type || 'text/plain',
        content: await file.text(),
        size: file.size,
      });
    }
    setAttachments((current) => {
      const combined = [
        ...current.filter((item) => !next.some((file) => file.name === item.name)),
        ...next,
      ];
      if (combined.length > 10) setAttachmentError('每次最多添加 10 个附件');
      return combined.slice(0, 10);
    });
  };

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
              {selectedSkills.map((skill) => (
                <span
                  key={skill.name}
                  className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-accent-border bg-accent-bg px-[8px] text-caption font-medium text-text-primary"
                >
                  <Sparkles size={12} className="text-accent" />
                  {skill.display_name ?? skill.name}
                  <button
                    type="button"
                    title="移除技能"
                    onClick={() => onToggleSkill(skill)}
                    className="grid h-[16px] w-[16px] place-items-center rounded-sm text-text-tertiary hover:bg-border-subtle hover:text-text-secondary"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {attachments.length > 0 && (
            <div className="flex flex-wrap items-center gap-[6px] px-[12px] pt-[8px]">
              {attachments.map((file) => (
                <span key={file.name} className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-border-default bg-surface-2 px-[8px] text-caption text-text-secondary">
                  <FileText size={12} />
                  <span className="max-w-[180px] truncate">{file.name}</span>
                  <button type="button" title="移除附件" onClick={() => setAttachments((items) => items.filter((item) => item.name !== file.name))} className="grid h-[16px] w-[16px] place-items-center rounded-sm text-text-tertiary hover:bg-border-subtle">
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="text/*,.csv,.json,.md,.yaml,.yml,.xml"
            className="hidden"
            onChange={(event) => {
              void addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="描述排产 / 调度 / 查询需求，输入 / 调用斜杠命令，或粘贴工单号 WO-…"
            className="block max-h-[120px] w-full resize-none border-none bg-transparent px-[15px] pb-[7px] pt-[13px] font-sans text-body leading-normal text-text-primary outline-none placeholder:text-text-tertiary"
          />
          <ComposerToolbar
            isStreaming={isStreaming}
            mode={mode}
            onClearSkills={onClearSkills}
            onImportSkill={onImportSkill}
            onTrustSkill={onTrustSkill}
            onModeChange={onModeChange}
            onRouteChange={onRouteChange}
            onStop={onStop}
            onSubmit={submit}
            onAddAttachment={() => fileInputRef.current?.click()}
            onToggleSkill={onToggleSkill}
            route={route}
            selectedSkills={selectedSkills}
            skills={skills}
          />
        </div>
        {attachmentError && <p className="mt-1 text-caption text-status-error">{attachmentError}</p>}
        <div className="mt-2 flex items-center gap-[7px] text-[11px] text-text-tertiary">
          {mode === 'auto' ? (
            <Zap size={12} className="text-auth-confirm" />
          ) : (
            <ShieldCheck size={12} className="text-text-tertiary" />
          )}
          <span>
            {route === 'auto' ? '引擎自动分类' : `指定 ${routeLabel}引擎`} ·{' '}
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
