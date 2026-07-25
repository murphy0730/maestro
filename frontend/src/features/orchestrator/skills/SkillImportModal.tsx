import { useRef, useState } from 'react';
import { FileArchive, Upload } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { importSkill, validateSkill } from '@/api';
import type { SkillMeta, SkillValidationReport } from '@/types';

export function SkillImportModal({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: (skill: SkillMeta) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState(false);
  const [progress, setProgress] = useState(0);
  const [report, setReport] = useState<SkillValidationReport>();
  const upload = async (file?: File) => {
    if (!file) return;
    if (!/\.(md|zip)$/i.test(file.name)) { setError('仅支持 .md 或 .zip Skill 包'); return; }
    if (file.size > 10 * 1024 * 1024) { setError('Skill 包不能超过 10 MB'); return; }
    setPending(true); setError(undefined); setProgress(0); setReport(undefined);
    try {
      const validation = await validateSkill(file);
      setReport(validation);
      if (!validation.compatible) { setError(validation.errors.join('；') || 'Skill 包不兼容'); return; }
      const imported = await importSkill(file, setProgress);
      onImported(imported); onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '导入失败'); }
    finally { setPending(false); }
  };
  return <Modal open={open} onClose={pending ? () => undefined : onClose} title="导入技能" subtitle="先校验，再写入宿主的 Skill 目录">
    <div className="space-y-4"><div className="rounded-md border border-dashed border-border-strong bg-surface-2 p-5 text-center"><FileArchive size={26} className="mx-auto text-accent" /><p className="mb-3 mt-2 text-body-sm text-text-secondary">Claude 兼容的 .md / .zip，最大 10 MB</p><input ref={input} type="file" accept=".md,.zip" className="hidden" onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ''; }} /><button type="button" disabled={pending} onClick={() => input.current?.click()} className="inline-flex h-8 items-center gap-2 rounded-md bg-blue-solid px-3 text-caption font-medium text-on-solid disabled:opacity-50"><Upload size={14} />{pending ? '正在处理…' : '选择技能文件'}</button></div>{pending && <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} className="h-1.5 overflow-hidden rounded-pill bg-surface-3"><span className="block h-full bg-accent transition-[width]" style={{ width: `${Math.max(8, progress * 100)}%` }} /></div>}{report && <p className={`m-0 text-caption ${report.compatible ? 'text-status-success' : 'text-status-error'}`}>{report.compatible ? `校验通过 · ${report.normalized_name ?? '兼容包'}` : '校验未通过'}</p>}{error && <p role="alert" className="m-0 rounded-md bg-status-error-bg p-3 text-caption text-status-error">{error}</p>}</div>
  </Modal>;
}
