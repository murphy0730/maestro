import { ProgressBar } from '@/components/ui/ProgressBar';

/** Per-file upload progress bar with error / ingesting states. */
export function UploadProgress({ fraction, error }: { fraction: number; error?: string }) {
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
