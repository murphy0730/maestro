import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Check, Copy, Download, FileText, RotateCw, Trash2 } from 'lucide-react';
import { API_BASE } from '@/api/client';
import type { SessionMessage } from '@/api/sessions';
import { TERMINAL_RUN_STATUSES, type RunProjection } from '@/stores/runStore';
import { BrandMark } from '@/components/ui/BrandMark';
import { Avatar } from '@/components/ui/Avatar';
import { Markdown } from '@/components/ui/Markdown';
import { StatusDot } from '@/components/ui/StatusDot';
import { ThinkingProcess } from './ThinkingProcess';

interface Props {
  messages: SessionMessage[];
  projection: RunProjection;
  loading: boolean;
  streaming: boolean;
  operatorName?: string;
  error?: string;
  onRetry?: () => void;
  onDeleteMessage?: (messageId: string, cascade: boolean) => void;
  onSuggestion: (text: string) => void;
}

/** 右键菜单锚定的是消息 id，不是渲染下标——下标会被并发写入错位。 */
interface MessageMenu {
  label: string;
  role: 'user' | 'assistant';
  content: string;
  /** 尚未落盘的消息（乐观发送、流式回答）没有 id，因此不可删除。 */
  messageId?: string;
  /** 消息所属的 Run；它还没停下来时不能删，否则后端会继续写一个没有提问的回合。 */
  runId?: string;
  cascade: boolean;
  x: number;
  y: number;
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
  onDeleteMessage,
  onSuggestion,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const [contextMenu, setContextMenu] = useState<MessageMenu>();
  const [copied, setCopied] = useState(false);
  const openMenu = (event: React.MouseEvent, menu: Omit<MessageMenu, 'x' | 'y'>) => {
    event.preventDefault();
    setCopied(false);
    setContextMenu({ ...menu, x: event.clientX, y: event.clientY });
  };
  // 运行还没停下就删掉它的提问，后端照跑不误，事后还会落一条无主的回答。
  const runStillLive = Boolean(
    projection.run &&
    !TERMINAL_RUN_STATUSES.has(projection.run.status) &&
    contextMenu?.runId === projection.run.run_id,
  );
  const canDelete = Boolean(onDeleteMessage && contextMenu?.messageId) && !runStillLive;
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
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(undefined);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [contextMenu]);
  return (
    <div
      ref={scrollRef}
      onScroll={(event) => {
        setContextMenu(undefined);
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
            <Message
              key={`${message.ts}-${index}`}
              message={message}
              operatorName={operatorName}
              onContextMenu={
                message.role === 'user' || message.role === 'assistant'
                  ? (event) =>
                      openMenu(event, {
                        label: `MSG ${String(index + 1).padStart(3, '0')}`,
                        role: message.role as 'user' | 'assistant',
                        content: message.content,
                        messageId: message.id,
                        runId: message.run_id ?? undefined,
                        // 删掉提问却留下回答，会让下一轮上下文里出现无主的 AI 发言。
                        cascade:
                          message.role === 'user' && messages[index + 1]?.role === 'assistant',
                      })
                  : undefined
              }
            />
          ))}
        {!loading && messages.length === 0 && !projection.run && (
          <EmptyState onSuggestion={onSuggestion} />
        )}
        {projection.run && !runCommitted && (
          <CurrentRun
            projection={projection}
            streaming={streaming}
            onContextMenu={(event) => {
              // 生成中的回答还没有 id，只能复制；没出字之前连菜单也不必开。
              const live = projection.run?.final_text || projection.tokens;
              if (!live) return;
              openMenu(event, { label: 'LIVE', role: 'assistant', content: live, cascade: false });
            }}
          />
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
      {contextMenu && (
        <div
          role="menu"
          aria-label="消息操作"
          className="material-popover fixed z-50 min-w-[176px] animate-[menu-in_.14s_cubic-bezier(.2,.8,.2,1)] rounded-md border border-border-subtle p-[4px] shadow-[var(--shadow-popover),inset_0_1px_0_var(--inset-hi)]"
          style={{
            left: Math.max(8, Math.min(contextMenu.x, window.innerWidth - 192)),
            top: Math.max(8, Math.min(contextMenu.y, window.innerHeight - 140)),
            transformOrigin: `${contextMenu.x > window.innerWidth - 192 ? 'right' : 'left'} ${contextMenu.y > window.innerHeight - 140 ? 'bottom' : 'top'}`,
          }}
          onPointerDown={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
          onKeyDown={(event) => {
            if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
            event.preventDefault();
            const items = Array.from(
              event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'),
            );
            const current = items.indexOf(document.activeElement as HTMLButtonElement);
            const next =
              event.key === 'ArrowDown'
                ? (current + 1) % items.length
                : (current - 1 + items.length) % items.length;
            items[next]?.focus();
          }}
        >
          <div className="hud-label flex items-center justify-between px-[8px] pb-[5px] pt-[4px] text-text-tertiary">
            <span>{contextMenu.label}</span>
            <span>{contextMenu.role === 'user' ? '操作员' : 'AGENT'}</span>
          </div>
          <div className="mx-[4px] mb-[4px] border-t border-border-subtle" />
          <button
            type="button"
            role="menuitem"
            autoFocus
            disabled={copied}
            onClick={() => {
              void copyText(contextMenu.content);
              setCopied(true);
              setTimeout(() => {
                setContextMenu(undefined);
                setCopied(false);
              }, 550);
            }}
            className={`flex w-full items-center gap-[8px] rounded-sm px-[8px] py-[6px] text-left text-caption transition-colors duration-fast ease-out ${
              copied
                ? 'text-status-success'
                : 'text-text-primary hover:bg-accent-bg hover:text-accent'
            }`}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? '已复制' : '复制'}
          </button>
          {runStillLive && Boolean(contextMenu.messageId) && (
            <>
              <div role="separator" className="mx-[4px] my-[4px] border-t border-border-subtle" />
              <p className="m-0 px-[8px] py-[6px] text-caption text-text-tertiary">
                运行进行中，请先停止再删除
              </p>
            </>
          )}
          {canDelete && (
            <>
              <div role="separator" className="mx-[4px] my-[4px] border-t border-border-subtle" />
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onDeleteMessage?.(contextMenu.messageId!, contextMenu.cascade);
                  setContextMenu(undefined);
                }}
                className="flex w-full items-center gap-[8px] rounded-sm px-[8px] py-[6px] text-left text-caption text-status-error transition-colors duration-fast ease-out hover:bg-status-error-bg"
              >
                <Trash2 size={14} />
                {contextMenu.cascade ? '删除该轮对话' : '删除消息'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

async function copyText(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through for Electron/file pages where Clipboard API permission is unavailable.
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}

function Message({
  message,
  operatorName,
  onContextMenu,
}: {
  message: SessionMessage;
  operatorName: string;
  onContextMenu?: React.MouseEventHandler<HTMLElement>;
}) {
  const user = message.role === 'user';
  return (
    <article
      onContextMenu={onContextMenu}
      className={`flex items-start gap-[10px] ${user ? 'justify-end' : ''}`}
    >
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

function CurrentRun({
  projection,
  streaming,
  onContextMenu,
}: {
  projection: RunProjection;
  streaming: boolean;
  onContextMenu?: React.MouseEventHandler<HTMLElement>;
}) {
  const run = projection.run!;
  const progress = Object.values(run.steps).map((step) => `${step.kind} · ${step.status}`);
  return (
    <article onContextMenu={onContextMenu} className="flex items-start gap-[10px]">
      <AgentMark />
      <div className="min-w-0 flex-1 text-body leading-[1.65] text-text-primary">
        <ThinkingProcess lines={progress} streaming={streaming} />
        {projection.resuming && (
          <p className="mb-[12px] flex items-center gap-[8px] text-body-sm text-text-secondary">
            <StatusDot tone={projection.resuming.approved ? 'accent' : 'danger'} pulse />
            {projection.resuming.approved ? '已确认 · 正在执行…' : '已拒绝 · 正在收尾…'}
          </p>
        )}
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
