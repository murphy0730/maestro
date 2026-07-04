import { useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import type { KnowledgeDoc } from '@/types';
import { useKnowledgeDocs, useReplaceKnowledge, useUploadKnowledge } from '@/api/hooks';
import { ContextPanel } from '@/components/ContextPanel';
import { Badge } from '@/components/ui/Badge';
import { SectionLabel } from '@/components/ui/panel';
import { DocRow } from './knowledge/DocRow';
import { UploadZone } from './knowledge/UploadZone';
import { errMessage, extOf, type UploadTask } from './knowledge/shared';

/**
 * KnowledgeManager — RAG 知识库管理面板 (增删改查编排壳)。
 * 视图拆在 ./knowledge/: UploadZone (拖拽上传 + 队列)、DocRow (单文档行)。
 * 本组件只持有上传任务状态与隐藏的 file input。
 */
interface PanelProps {
  onClose?: () => void;
}

export function KnowledgeManager({ onClose }: PanelProps) {
  const { data, isLoading, error } = useKnowledgeDocs();
  const upload = useUploadKnowledge();
  const replace = useReplaceKnowledge();

  const [tasks, setTasks] = useState<UploadTask[]>([]);
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

      <UploadZone
        supported={supported}
        tasks={tasks}
        onPickFiles={onPickFiles}
        onRemoveTask={(id) => setTasks((ts) => ts.filter((x) => x.id !== id))}
        onBrowse={() => fileInput.current?.click()}
      />

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
