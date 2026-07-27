import { useEffect, useRef } from 'react';
import { AlertCircle, Download, FileText, RotateCw } from 'lucide-react';
import { API_BASE } from '@/api/client';
import type { SessionMessage } from '@/api/sessions';
import type { RunProjection } from '@/stores/runStore';
import { BrandMark } from '@/components/ui/BrandMark';
import { Avatar } from '@/components/ui/Avatar';
import { Markdown } from '@/components/ui/Markdown';
import { ThinkingProcess } from './ThinkingProcess';

interface Props {
  messages: SessionMessage[];
  projection: RunProjection;
  loading: boolean;
  streaming: boolean;
  operatorName?: string;
  error?: string;
  onRetry?: () => void;
  onSuggestion: (text: string) => void;
}

/** 设计稿 .m-sys .av：等宽 AI 字标，替代通用机器人图标。 */
function AgentMark() {
  return (
    <span
      aria-hidden="true"
      className="grid h-[24px] w-[24px] flex-none place-items-center rounded-md border border-accent-border bg-accent-bg font-mono text-[9px] font-bold tracking-[0.04em] text-accent shadow-glow-accent"
    >
      AI
    </span>
  );
}

export function ConversationPanel({
  messages,
  projection,
  loading,
  streaming,
  operatorName = '周文涛',
  error,
  onRetry,
  onSuggestion,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const runCommitted = Boolean(
    projection.run &&
    messages.some(
      (message) => message.role === 'assistant' && message.run_id === projection.run?.run_id,
    ),
  );
  useEffect(() => {
    const element = scrollRef.current;
    if (element && pinnedRef.current && typeof element.scrollTo === 'function')
      element.scrollTo({ top: element.scrollHeight, behavior: streaming ? 'auto' : 'smooth' });
  }, [messages, projection.tokens, projection.run?.final_text, streaming]);
  return (
    <div
      ref={scrollRef}
      onScroll={(event) => {
        const element = event.currentTarget;
        pinnedRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 96;
      }}
      className={`min-h-0 flex-1 overflow-y-auto px-[26px] py-[22px] ${streaming ? 'streaming-scan' : ''}`}
    >
      <div className="mx-auto flex max-w-[640px] flex-col gap-[16px]">
        {loading && (
          <div role="status" className="pt-[96px] text-center text-caption text-text-tertiary">
            正在载入会话历史…
          </div>
        )}
        {!loading &&
          messages.map((message, index) => (
            <Message key={`${message.ts}-${index}`} message={message} operatorName={operatorName} />
          ))}
        {!loading && messages.length === 0 && !projection.run && (
          <EmptyState onSuggestion={onSuggestion} />
        )}
        {projection.run && !runCommitted && (
          <CurrentRun projection={projection} streaming={streaming} />
        )}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-[8px] rounded-md border border-status-error/30 bg-status-error-bg p-[12px] text-caption text-status-error"
          >
            <AlertCircle size={15} className="mt-[2px] flex-none" />
            <span className="flex-1">{error}</span>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-[4px] text-text-primary"
              >
                <RotateCw size={13} />
                重试
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Message({ message, operatorName }: { message: SessionMessage; operatorName: string }) {
  const user = message.role === 'user';
  return (
    <article className={`flex items-start gap-[10px] ${user ? 'justify-end' : ''}`}>
      {!user && <AgentMark />}
      <div
        className={`min-w-0 ${user ? 'user-bubble max-w-[82%] rounded-[12px_12px_4px_12px] px-[14px] py-[10px]' : 'max-w-[calc(100%-34px)]'} text-body leading-[1.65] text-text-primary`}
      >
        <Markdown>{message.content}</Markdown>
        {message.skill_names && message.skill_names.length > 0 && (
          <div className="mt-[8px] font-mono text-[10px] text-text-tertiary">
            SKILLS · {message.skill_names.join(' · ')}
          </div>
        )}
        {message.artifact_ids && message.artifact_ids.length > 0 && (
          <ArtifactLinks ids={message.artifact_ids} />
        )}
      </div>
      {user && <Avatar name={operatorName} size={24} className="mt-px" />}
    </article>
  );
}

function CurrentRun({ projection, streaming }: { projection: RunProjection; streaming: boolean }) {
  const run = projection.run!;
  const progress = Object.values(run.steps).map((step) => `${step.kind} · ${step.status}`);
  return (
    <article className="flex items-start gap-[10px]">
      <AgentMark />
      <div className="min-w-0 flex-1 text-body leading-[1.65] text-text-primary">
        <ThinkingProcess lines={progress} streaming={streaming} />
        {projection.upgradeReason && (
          <div className="controlled-path mb-[12px] rounded-r-md border-l-2 border-path-controlled px-[12px] py-[8px] text-caption">
            已因 {projection.upgradeReason} 升级为受控执行，关键动作将请求确认。
          </div>
        )}
        {projection.tokens && (
          <div>
            <Markdown>{projection.tokens}</Markdown>
            {streaming && (
              <span data-testid="streaming-caret" className="streaming-caret" aria-hidden="true" />
            )}
          </div>
        )}
        {run.final_text && run.final_text !== projection.tokens && (
          <Markdown>{run.final_text}</Markdown>
        )}
        {!projection.tokens && !run.final_text && (
          <p className="m-0 text-text-secondary">{statusText(run.status)}</p>
        )}
        {projection.recovered && (
          <p className="mt-[8px] font-mono text-[10px] text-status-success">
            RECOVERED · 已从运行快照恢复
          </p>
        )}
        {run.input_artifact_ids && run.input_artifact_ids.length > 0 && (
          <ArtifactLinks ids={run.input_artifact_ids} />
        )}
      </div>
    </article>
  );
}

function ArtifactLinks({ ids }: { ids: string[] }) {
  return (
    <div className="mt-[8px] flex flex-wrap gap-[8px]">
      {ids.map((id) => (
        <a
          key={id}
          href={`${API_BASE}/artifacts/${encodeURIComponent(id)}`}
          target="_blank"
          rel="noreferrer"
          download
          className="inline-flex items-center gap-[4px] rounded-md border border-border-default bg-surface-2 px-[8px] py-[4px] text-caption text-accent hover:border-accent"
        >
          <FileText size={12} />
          <span className="max-w-36 truncate">产物 {id.slice(0, 10)}</span>
          <Download size={11} />
        </a>
      ))}
    </div>
  );
}

function EmptyState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  const suggestions = ['重排未来三天的注塑工单', '分析上周夜班产能瓶颈', '跟进缺料催料进度'];
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-[14px] text-center">
      <BrandMark size={46} />
      <h2 className="m-0 text-[30px] font-bold tracking-[0.02em] text-text-primary">
        制造执行 Agent
      </h2>
      <p className="m-0 max-w-[420px] text-body-sm leading-[1.65] text-text-secondary">
        选择模式、挂载技能，然后描述任务——Agent 自主拆解、执行，并在关键写入前请求你的确认。
      </p>
      <div className="mt-[6px] flex flex-wrap justify-center gap-[8px]">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="rounded-pill border border-border-subtle bg-surface-2 px-[12px] py-[4px] text-caption text-text-secondary transition-colors duration-fast ease-out hover:border-accent hover:text-accent"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function statusText(status: string) {
  return (
    (
      {
        created: '任务已创建，正在选择执行路径…',
        running_fast: '正在快速执行…',
        structuring: '正在构建受控计划…',
        running_structured: '正在执行受控计划…',
        waiting_approval: '运行已暂停，等待你的审批。',
        waiting_external: '正在等待外部系统返回。',
        reconciling: '正在对账外部执行结果。',
        cancelling: '正在停止运行…',
        cancelled: '运行已取消。',
        failed: '运行失败，请查看详情。',
        completed: '运行已完成。',
      } as Record<string, string>
    )[status] ?? status
  );
}
