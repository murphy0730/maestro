import { useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import type { KnowledgeDoc } from '@/types';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { ApiError } from '@/api/client';
import {
  useDeleteKnowledge,
  useKnowledgeDocs,
  useRenameKnowledge,
  useReplaceKnowledge,
  useUploadKnowledge,
} from '@/api/hooks';
import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { SectionLabel } from '@/components/ui/panel';

/* ------------------------------------------------------------------ helpers */

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function extOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot).toLowerCase() : '';
}

function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return '操作失败';
}

/** An in-flight upload (new file) with its live progress. */
interface UploadTask {
  id: string;
  name: string;
  fraction: number;
  error?: string;
}

/* ------------------------------------------------------------ progress bar */

function UploadProgress({ fraction, error }: { fraction: number; error?: string }) {
  const pct = Math.round(fraction * 100);
  return (
    <div className="mt-[6px]">
      <ProgressBar
        percent={error ? 100 : pct}
        fillClassName={error ? 'bg-status-error' : 'bg-query'}
      />
      <div
        className={`mt-[3px] font-mono text-micro ${error ? 'text-status-error' : 'text-text-tertiary'}`}
      >
        {error ? error : pct < 100 ? `上传中 ${pct}%` : '入库中…'}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- doc row */

interface DocRowProps {
  doc: KnowledgeDoc;
  onReplace: (doc: KnowledgeDoc) => void;
  replacing?: number; // 0–1 while a replace upload is running, else undefined
}

function DocRow({ doc, onReplace, replacing }: DocRowProps) {
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

/* --------------------------------------------------------------- panel */

interface PanelProps {
  onClose?: () => void;
}

export function KnowledgeManager({ onClose }: PanelProps) {
  const { data, isLoading, error } = useKnowledgeDocs();
  const upload = useUploadKnowledge();
  const replace = useReplaceKnowledge();

  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [dragging, setDragging] = useState(false);
  const [replacingId, setReplacingId] = useState<{ id: string; fraction: number } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const replaceTarget = useRef<KnowledgeDoc | null>(null);

  const supported = data?.supported_extensions ?? [];
  const accept = supported.join(',');
  const docs = data?.docs ?? [];

  const patchTask = (id: string, patch: Partial<UploadTask>) =>
    setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  const startUploads = async (files: File[]) => {
    for (const file of files) {
      const id = `up-${Math.random().toString(36).slice(2, 8)}`;
      if (supported.length && !supported.includes(extOf(file.name))) {
        setTasks((ts) => [
          ...ts,
          { id, name: file.name, fraction: 0, error: `不支持的类型 ${extOf(file.name)}` },
        ]);
        continue;
      }
      setTasks((ts) => [...ts, { id, name: file.name, fraction: 0 }]);
      try {
        await upload.mutateAsync({
          file,
          opts: { onProgress: (f) => patchTask(id, { fraction: f }) },
        });
        setTasks((ts) => ts.filter((t) => t.id !== id)); // done → drop from queue
      } catch (e) {
        patchTask(id, { error: errMessage(e) });
      }
    }
  };

  const onPickFiles = (list: FileList | null) => {
    if (list && list.length) startUploads(Array.from(list));
  };

  const onReplace = (doc: KnowledgeDoc) => {
    replaceTarget.current = doc;
    replaceInput.current?.click();
  };

  const onReplaceFile = async (list: FileList | null) => {
    const doc = replaceTarget.current;
    const file = list?.[0];
    replaceTarget.current = null;
    if (!doc || !file) return;
    setReplacingId({ id: doc.doc_id, fraction: 0 });
    try {
      await replace.mutateAsync({
        docId: doc.doc_id,
        file,
        opts: { onProgress: (f) => setReplacingId({ id: doc.doc_id, fraction: f }) },
      });
    } finally {
      setReplacingId(null);
    }
  };

  const totalChunks = docs.reduce((s, d) => s + d.chunk_count, 0);
  const stats = `${docs.length} 篇 · ${totalChunks} 片段`;

  return (
    <ContextPanel
      eyebrow="查询引擎 · RAG 知识库"
      title="知识库管理"
      badge={
        <Badge tone="query" dot glow>
          增删改查
        </Badge>
      }
      onClose={onClose}
    >
      {/* hidden inputs */}
      <input
        ref={fileInput}
        type="file"
        multiple
        accept={accept}
        className="hidden"
        onChange={(e) => {
          onPickFiles(e.target.files);
          e.target.value = '';
        }}
      />
      <input
        ref={replaceInput}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          onReplaceFile(e.target.files);
          e.target.value = '';
        }}
      />

      {/* dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onPickFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        className={`flex cursor-pointer flex-col items-center gap-[6px] rounded-md border border-dashed px-4 py-6 text-center transition-colors ${
          dragging ? 'border-query bg-query-bg' : 'border-border-strong bg-surface-inset'
        }`}
      >
        <span className="grid h-[34px] w-[34px] place-items-center rounded-md border border-query-border bg-query-bg text-query-fg">
          <Upload size={16} />
        </span>
        <div className="text-body-sm font-semibold text-text-primary">拖拽文件到此，或点击选择</div>
        <div className="font-mono text-micro text-text-tertiary">
          支持 {supported.length ? supported.join(' · ') : '加载中…'}
        </div>
      </div>

      {/* in-flight uploads */}
      {tasks.length > 0 && (
        <div>
          <SectionLabel>上传队列</SectionLabel>
          <div className="flex flex-col gap-2">
            {tasks.map((t) => (
              <div
                key={t.id}
                className="rounded-md border border-border-default bg-surface-inset p-3"
              >
                <div className="flex items-center gap-2">
                  {t.error ? (
                    <AlertTriangle size={13} className="text-status-error" />
                  ) : (
                    <Loader2 size={13} className="animate-spin text-query-fg" />
                  )}
                  <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-body-sm text-text-primary">
                    {t.name}
                  </span>
                  {t.error && (
                    <button
                      onClick={() => setTasks((ts) => ts.filter((x) => x.id !== t.id))}
                      className="text-text-tertiary hover:text-text-secondary"
                      aria-label="移除"
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>
                <UploadProgress fraction={t.fraction} error={t.error} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* document list */}
      <div>
        <SectionLabel
          right={<span className="font-mono text-[10.5px] text-text-tertiary">{stats}</span>}
        >
          知识库文档
        </SectionLabel>

        {isLoading && (
          <div className="py-6 text-center text-body-sm text-text-tertiary">加载中…</div>
        )}
        {error && (
          <div className="flex items-center gap-[6px] rounded-md border border-status-error/40 bg-status-error-bg px-3 py-2 text-body-sm text-status-error">
            <AlertTriangle size={13} />
            {errMessage(error)}
          </div>
        )}
        {!isLoading && !error && docs.length === 0 && (
          <div className="py-6 text-center text-body-sm text-text-tertiary">
            知识库为空，上传文件开始构建。
          </div>
        )}

        <div className="flex flex-col gap-2">
          {docs.map((doc) => (
            <DocRow
              key={doc.doc_id}
              doc={doc}
              onReplace={onReplace}
              replacing={replacingId?.id === doc.doc_id ? replacingId.fraction : undefined}
            />
          ))}
        </div>
      </div>
    </ContextPanel>
  );
}
