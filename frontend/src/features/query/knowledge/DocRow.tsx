import { useState } from 'react';
import { AlertTriangle, Check, FileText, Pencil, RefreshCw, Trash2, X } from 'lucide-react';
import type { KnowledgeDoc } from '@/types';
import { useDeleteKnowledge, useRenameKnowledge } from '@/api/hooks';
import { Badge } from '@/components/ui/Badge';
import { UploadProgress } from './UploadProgress';
import { formatBytes } from './shared';

/** One knowledge document: name (inline-renamable), stats, replace/delete. */
interface DocRowProps {
  doc: KnowledgeDoc;
  onReplace: (doc: KnowledgeDoc) => void;
  replacing?: number; // 0–1 while a replace upload is running, else undefined
}

export function DocRow({ doc, onReplace, replacing }: DocRowProps) {
  const rename = useRenameKnowledge();
  const del = useDeleteKnowledge();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(doc.name);
  const [confirming, setConfirming] = useState(false);

  const failed = doc.status === 'failed';

  const submitRename = () => {
    const name = draft.trim();
    if (name && name !== doc.name) rename.mutate({ docId: doc.doc_id, name });
    setEditing(false);
  };

  return (
    <div className="rounded-md border border-border-default bg-surface-inset p-3">
      <div className="flex items-center gap-2">
        <span className="grid h-[26px] w-[26px] flex-none place-items-center rounded-xs border border-query-border bg-query-bg text-query-fg">
          <FileText size={13} />
        </span>

        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={submitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitRename();
              if (e.key === 'Escape') setEditing(false);
            }}
            className="min-w-0 flex-1 rounded-sm border border-query-border bg-surface-2 px-2 py-1 text-body-sm text-text-primary outline-none"
          />
        ) : (
          <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-body-sm font-semibold text-text-primary">
            {doc.name}
          </span>
        )}

        <span className="flex-none font-mono text-micro uppercase text-query-fg">{doc.type}</span>
      </div>

      <div className="mt-[6px] flex items-center gap-2 pl-[34px] font-mono text-micro text-text-tertiary">
        <span>{doc.chunk_count} 片段</span>
        <span>·</span>
        <span>{formatBytes(doc.bytes)}</span>
        {failed && (
          <Badge tone="error" dot>
            未入库
          </Badge>
        )}
      </div>

      {failed && (
        <div className="mt-[6px] flex items-center gap-[6px] pl-[34px] text-[11px] text-status-error">
          <AlertTriangle size={11} />
          嵌入未配置，该文档未参与检索。
        </div>
      )}

      {replacing !== undefined && <UploadProgress fraction={replacing} />}

      {/* actions */}
      {!confirming ? (
        <div className="mt-[10px] flex gap-[6px] pl-[34px]">
          <RowButton
            icon={<Pencil size={11} />}
            label="重命名"
            onClick={() => {
              setDraft(doc.name);
              setEditing(true);
            }}
          />
          <RowButton icon={<RefreshCw size={11} />} label="换内容" onClick={() => onReplace(doc)} />
          <RowButton
            icon={<Trash2 size={11} />}
            label="删除"
            danger
            onClick={() => setConfirming(true)}
          />
        </div>
      ) : (
        <div className="mt-[10px] flex items-center gap-[6px] pl-[34px]">
          <span className="text-[11px] text-text-secondary">确认删除？</span>
          <button
            onClick={() => {
              del.mutate(doc.doc_id);
              setConfirming(false);
            }}
            className="inline-flex items-center gap-1 rounded-sm border border-status-error/50 bg-status-error-bg px-2 py-[3px] text-[11px] font-semibold text-status-error"
          >
            <Check size={11} /> 删除
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="inline-flex items-center gap-1 rounded-sm border border-border-default px-2 py-[3px] text-[11px] text-text-secondary"
          >
            <X size={11} /> 取消
          </button>
        </div>
      )}
    </div>
  );
}

function RowButton({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-[3px] text-[11px] font-medium ${
        danger
          ? 'border-border-default text-text-tertiary hover:border-status-error/50 hover:text-status-error'
          : 'border-border-default text-text-secondary hover:border-query-border hover:text-query-fg'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
