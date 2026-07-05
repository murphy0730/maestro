import { useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { UploadProgress } from '@/features/query/knowledge/UploadProgress';
import { errMessage, extOf } from '@/features/query/knowledge/shared';
import { useImportSkill } from '@/api';
import type { SkillMeta } from '@/types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (s: SkillMeta) => void;
}

export function SkillImportModal({ open, onClose, onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fraction, setFraction] = useState(0);
  const { mutateAsync, isPending, error } = useImportSkill();

  async function upload(file: File) {
    if (!/^\.(zip|md)$/i.test(extOf(file.name))) {
      return; // 客户端预检后缀;后端兜底 415
    }
    setFraction(0);
    try {
      const meta = await mutateAsync(file);
      onImported(meta);
      onClose();
    } catch {
      // error 由 useImportSkill.error 承载
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="导入技能" widthClassName="w-[560px]">
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
            if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
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
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
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
