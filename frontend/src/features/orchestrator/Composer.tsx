import { useRef, useState } from 'react';
import { FileText, Sparkles, X } from 'lucide-react';
import type { SkillMeta } from '@/types';
import { ComposerToolbar } from './ComposerToolbar';

interface ComposerProps {
  onSend: (text: string, attachments: File[]) => void;
  expert: boolean;
  onExpertChange: (expert: boolean) => void;
  disabled?: boolean; isStreaming?: boolean; onStop?: () => void;
  skills: SkillMeta[]; selectedSkills: SkillMeta[];
  onToggleSkill: (skill: SkillMeta) => void; onClearSkills: () => void; onImportSkill: () => void; onTrustSkill?: (skill: SkillMeta) => void;
}
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export function Composer({ onSend, expert, onExpertChange, disabled = false, isStreaming = false, onStop, skills, selectedSkills, onToggleSkill, onClearSkills, onImportSkill, onTrustSkill }: ComposerProps) {
  const [draft, setDraft] = useState(''); const [attachments, setAttachments] = useState<File[]>([]); const [attachmentError, setAttachmentError] = useState(''); const fileInputRef = useRef<HTMLInputElement>(null);
  const submit = () => { if (isStreaming || disabled || !draft.trim()) return; onSend(draft.trim(), attachments); setDraft(''); setAttachments([]); onClearSkills(); };
  const addFiles = (files: FileList | null) => { if (!files) return; const acceptable = Array.from(files).filter((file) => file.size <= MAX_ATTACHMENT_BYTES); if (acceptable.length !== files.length) setAttachmentError('附件不能超过 10 MB'); else setAttachmentError(''); setAttachments((current) => [...current.filter((item) => !acceptable.some((file) => file.name === item.name)), ...acceptable].slice(0, 10)); };
  return <div className="flex-none px-[30px] pb-[18px] pt-2"><div className="pointer-events-auto mx-auto max-w-[760px]"><div className="material-dock rounded-lg border border-border-default shadow-elev-2">
    {selectedSkills.length > 0 && <div className="flex flex-wrap gap-[6px] px-[12px] pt-[10px]">{selectedSkills.map((skill) => <span key={skill.name} className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-accent-border bg-accent-bg px-[8px] text-caption"><Sparkles size={12} className="text-accent" />{skill.display_name ?? skill.name}<button type="button" title="移除技能" onClick={() => onToggleSkill(skill)}><X size={12} /></button></span>)}</div>}
    {attachments.length > 0 && <div className="flex flex-wrap gap-[6px] px-[12px] pt-[8px]">{attachments.map((file) => <span key={file.name} className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-border-default bg-surface-2 px-[8px] text-caption"><FileText size={12} />{file.name}<button type="button" title="移除附件" onClick={() => setAttachments((items) => items.filter((item) => item.name !== file.name))}><X size={12} /></button></span>)}</div>}
    <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(event) => { addFiles(event.target.files); event.target.value = ''; }} />
    <textarea disabled={disabled} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }} rows={1} placeholder={disabled ? '正在加载会话…' : '描述要完成的制造任务，或附加资料'} className="block max-h-[120px] w-full resize-none border-none bg-transparent px-[15px] pb-[7px] pt-[13px] font-sans text-body leading-normal text-text-primary outline-none placeholder:text-text-tertiary" />
    <ComposerToolbar disabled={disabled} isStreaming={isStreaming} expert={expert} onExpertChange={onExpertChange} onClearSkills={onClearSkills} onImportSkill={onImportSkill} onTrustSkill={onTrustSkill} onStop={onStop} onSubmit={submit} onAddAttachment={() => fileInputRef.current?.click()} onToggleSkill={onToggleSkill} selectedSkills={selectedSkills} skills={skills} />
  </div>{attachmentError && <p className="mt-1 text-caption text-status-error">{attachmentError}</p>}<div className="mt-2 text-[11px] text-text-tertiary">Agent 会按权限策略执行，所有写入操作均需确认</div></div></div>;
}
