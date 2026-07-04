import { useState } from 'react';
import { AlertTriangle, Loader2, Upload, X } from 'lucide-react';
import { SectionLabel } from '@/components/ui/panel';
import { UploadProgress } from './UploadProgress';
import type { UploadTask } from './shared';

/** Drag-and-drop / click dropzone plus the in-flight upload queue. */
interface UploadZoneProps {
  supported: string[];
  tasks: UploadTask[];
  onPickFiles: (files: FileList | null) => void;
  onRemoveTask: (id: string) => void;
  onBrowse: () => void;
}

export function UploadZone({ supported, tasks, onPickFiles, onRemoveTask, onBrowse }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);

  return (
    <>
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
        onClick={onBrowse}
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
                      onClick={() => onRemoveTask(t.id)}
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
    </>
  );
}
