import { useRef, useState } from 'react';
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
    <Modal open={open} onClose={onClose} title="导入技能">
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
        className={`cursor-pointer rounded-lg border border-dashed p-6 text-center text-body-sm ${
          dragging ? 'border-accent-border bg-accent-bg' : 'border-border-default'
        }`}
      >
        拖拽 .zip / .md 技能包到此，或点击选择
        <input
          ref={inputRef}
          type="file"
          accept=".zip,.md"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
      </div>
      {isPending && <UploadProgress fraction={fraction} fillClassName="bg-accent" />}
      {error && (
        <div className="mt-2 text-[12px] text-status-error">
          技能包不符合规范：{errMessage(error)}
        </div>
      )}
    </Modal>
  );
}
