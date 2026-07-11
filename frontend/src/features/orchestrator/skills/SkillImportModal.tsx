import { useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, UploadCloud } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { UploadProgress } from '@/features/query/knowledge/UploadProgress';
import { errMessage, extOf } from '@/features/query/knowledge/shared';
import { trustSkill, useImportSkill, validateSkill } from '@/api';
import type { SkillMeta, SkillValidationReport } from '@/types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (s: SkillMeta) => void;
}

export function SkillImportModal({ open, onClose, onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fraction, setFraction] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [report, setReport] = useState<SkillValidationReport | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [importedMeta, setImportedMeta] = useState<SkillMeta | null>(null);
  const [trusting, setTrusting] = useState(false);
  const { mutateAsync, isPending, error } = useImportSkill();

  async function preflight(file: File) {
    if (!/^\.(zip|md)$/i.test(extOf(file.name))) {
      return; // 客户端预检后缀;后端兜底 415
    }
    setSelectedFile(file);
    setReport(null);
    setValidationError(null);
    setValidating(true);
    try {
      setReport(await validateSkill(file));
    } catch (err) {
      setValidationError(errMessage(err));
    } finally {
      setValidating(false);
    }
  }

  async function upload() {
    if (!selectedFile || !report?.compatible) return;
    setFraction(0);
    try {
      const meta = await mutateAsync({ file: selectedFile, opts: { onProgress: setFraction } });
      if (meta.scripts?.length) {
        setImportedMeta(meta);
      } else {
        onImported(meta);
        onClose();
      }
    } catch {
      // error 由 useImportSkill.error 承载
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="导入技能" widthClassName="max-w-[560px]">
      <div className="px-2 py-1">
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (e.dataTransfer.files[0]) preflight(e.dataTransfer.files[0]);
          }}
          className={`flex cursor-pointer flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center transition-colors ${
            dragging
              ? 'border-accent-border bg-accent-bg'
              : 'border-border-default hover:bg-border-subtle'
          }`}
        >
          <UploadCloud size={30} className="text-text-tertiary" strokeWidth={1.5} />
          <span className="text-body-sm font-medium text-text-primary">
            拖拽技能包到此，或点击选择文件
          </span>
          <span className="text-[12px] text-text-tertiary">支持 .md 与 .zip 格式</span>
          <input
            ref={inputRef}
            type="file"
            accept=".zip,.md"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && preflight(e.target.files[0])}
          />
        </div>

        <ul className="mt-5 space-y-2 text-[12px] leading-relaxed text-text-secondary">
          <li className="flex gap-2">
            <span className="text-text-tertiary">·</span>
            <span>
              <span className="font-medium text-text-primary">.md 单文件</span>
              ：须以 YAML frontmatter 开头，含 name、description 字段
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-text-tertiary">·</span>
            <span>
              <span className="font-medium text-text-primary">.zip 技能包</span>
              ：根目录须含 SKILL.md，整包不超过 10MB
            </span>
          </li>
        </ul>

        {validating && <div className="mt-4 text-[12px] text-text-secondary">正在检查兼容性…</div>}
        {validationError && (
          <div className="mt-4 text-[12px] text-status-error">预检失败：{validationError}</div>
        )}
        {report && (
          <div className="mt-4 rounded-lg border border-border-default bg-bg-secondary p-4 text-[12px]">
            <div className="flex items-center gap-2 font-medium text-text-primary">
              {report.compatible ? (
                <CheckCircle2 size={16} className="text-status-success" />
              ) : (
                <AlertTriangle size={16} className="text-status-error" />
              )}
              {report.compatible ? `可导入为 ${report.normalized_name}` : '该技能包暂不兼容'}
            </div>
            <div className="mt-2 text-text-secondary">
              能力：提示词 · {report.capabilities.attachments ? '附件' : '无附件'} ·{' '}
              {report.capabilities.scripts ? '脚本仅保存、默认不执行' : '无脚本'}
            </div>
            {Object.keys(report.tool_mapping).length > 0 && (
              <div className="mt-2 text-text-secondary">
                工具映射：
                {Object.entries(report.tool_mapping)
                  .map(([from, to]) => `${from} → ${to}`)
                  .join('，')}
              </div>
            )}
            {[...report.warnings, ...report.errors].map((message) => (
              <div key={message} className="mt-1 text-text-tertiary">
                · {message}
              </div>
            ))}
          </div>
        )}

        {report?.compatible && (
          <button
            type="button"
            onClick={upload}
            disabled={isPending}
            className="mt-4 w-full rounded-lg bg-accent px-4 py-2 text-body-sm font-medium text-white disabled:opacity-50"
          >
            {isPending ? '正在导入…' : '确认导入'}
          </button>
        )}

        {importedMeta && (
          <div className="mt-4 rounded-lg border border-status-warning/40 bg-status-warning-bg p-4 text-[12px]">
            <div className="font-medium text-text-primary">技能已导入，脚本尚未信任</div>
            <div className="mt-1 break-all text-text-secondary">
              当前包 hash：{importedMeta.package_sha256}
            </div>
            <div className="mt-1 text-text-secondary">
              信任后脚本每次仍需权限确认；优先在 SRT 沙箱执行，SRT
              不可用时可在确认后于宿主机受控执行。
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={trusting}
                onClick={async () => {
                  setTrusting(true);
                  try {
                    const trust = await trustSkill(importedMeta.name, importedMeta.package_sha256);
                    onImported({ ...importedMeta, trust });
                    onClose();
                  } catch (err) {
                    setValidationError(errMessage(err));
                  } finally {
                    setTrusting(false);
                  }
                }}
                className="rounded-md bg-accent px-3 py-2 font-medium text-white disabled:opacity-50"
              >
                {trusting ? '正在信任…' : '信任当前版本并使用'}
              </button>
              <button
                type="button"
                onClick={() => {
                  onImported(importedMeta);
                  onClose();
                }}
                className="rounded-md border border-border-default px-3 py-2 text-text-secondary"
              >
                保持未信任
              </button>
            </div>
          </div>
        )}

        {isPending && (
          <div className="mt-4">
            <UploadProgress fraction={fraction} fillClassName="bg-accent" />
          </div>
        )}
        {error && (
          <div className="mt-4 text-[12px] text-status-error">
            技能包不符合规范：{errMessage(error)}
          </div>
        )}
      </div>
    </Modal>
  );
}
