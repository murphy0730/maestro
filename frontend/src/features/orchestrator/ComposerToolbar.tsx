import { useState } from 'react';
import { Paperclip, ShieldCheck, Square, Zap } from 'lucide-react';
import type { SkillMeta } from '@/types';
import { Button } from '@/components/ui/Button';
import { SendIcon } from '@/components/ui/Icon';
import { SkillMenu } from './skills/SkillMenu';
interface Props { disabled?: boolean; onAddAttachment: () => void; isStreaming: boolean; expert: boolean; onExpertChange: (value: boolean) => void; onClearSkills: () => void; onImportSkill: () => void; onTrustSkill?: (skill: SkillMeta) => void; onStop?: () => void; onSubmit: () => void; onToggleSkill: (skill: SkillMeta) => void; selectedSkills: SkillMeta[]; skills: SkillMeta[] }
export function ComposerToolbar({ disabled, onAddAttachment, isStreaming, expert, onExpertChange, onClearSkills, onImportSkill, onTrustSkill, onStop, onSubmit, onToggleSkill, selectedSkills, skills }: Props) {
  const [skillOpen, setSkillOpen] = useState(false);
  return <div className="flex items-center gap-2 px-[10px] py-2"><button type="button" onClick={onAddAttachment} title="添加文件" className="grid h-[30px] w-[30px] place-items-center rounded-sm text-text-tertiary hover:bg-surface-3"><Paperclip size={16} /></button><span className="h-[18px] w-px bg-border-default" /><button type="button" onClick={() => onExpertChange(!expert)} className="inline-flex h-[26px] items-center gap-1 rounded-sm border border-border-default bg-surface-2 px-2 text-caption text-text-secondary">{expert ? <Zap size={13} className="text-accent" /> : <ShieldCheck size={13} />}专家上下文</button><SkillMenu skills={skills} selected={selectedSkills} onToggleSkill={onToggleSkill} onClear={onClearSkills} onImportSkill={onImportSkill} onTrustSkill={onTrustSkill} open={skillOpen} onToggle={() => setSkillOpen((open) => !open)} /><span className="flex-1" />{isStreaming ? <Button variant="danger" onClick={onStop} leadingIcon={<Square size={12} fill="currentColor" />}>停止</Button> : <button type="button" disabled={disabled} onClick={onSubmit} aria-label="发送消息" className="grid h-[30px] w-[30px] place-items-center rounded-sm bg-blue-solid text-on-solid disabled:opacity-50"><SendIcon size={15} /></button>}</div>;
}
