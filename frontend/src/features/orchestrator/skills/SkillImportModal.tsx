import { useRef, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { importSkill } from '@/api';
import type { SkillMeta } from '@/types';

export function SkillImportModal({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: (skill: SkillMeta) => void }) {
  const input = useRef<HTMLInputElement>(null); const [error, setError] = useState<string>(); const [pending, setPending] = useState(false);
  const upload = async (file?: File) => { if (!file) return; setPending(true); setError(undefined); try { onImported(await importSkill(file)); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : '导入失败'); } finally { setPending(false); } };
  return <Modal open={open} onClose={onClose} title="导入技能"><div className="space-y-3"><p className="m-0 text-body-sm text-text-secondary">导入 Claude 兼容的 .md 或 .zip Skill 包。</p><input ref={input} type="file" accept=".md,.zip" className="hidden" onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ''; }} /><button type="button" disabled={pending} onClick={() => input.current?.click()} className="h-control rounded-sm border border-border-default px-3 text-body-sm text-text-primary disabled:opacity-50">{pending ? '正在导入…' : '选择技能文件'}</button>{error && <p role="alert" className="m-0 text-caption text-status-error">{error}</p>}</div></Modal>;
}
