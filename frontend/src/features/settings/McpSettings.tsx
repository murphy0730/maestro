import { useState } from 'react';
import { Plug, Plus, RefreshCw, Trash2, TriangleAlert } from 'lucide-react';
import {
  useDeleteMcpServer,
  useMcpServers,
  useReconnectMcpServer,
  useUpsertMcpServer,
} from '@/api';
import { ApiError } from '@/api';
import type { McpServer, McpStatus } from '@/types';

const STATUS_LABEL: Record<McpStatus, string> = {
  connected: '已连接',
  disconnected: '未启用',
  error: '连接失败',
};

const STATUS_CLASS: Record<McpStatus, string> = {
  connected: 'text-status-success',
  disconnected: 'text-text-tertiary',
  error: 'text-status-danger',
};

/** 403 means the privileged token is missing or mismatched — say so plainly. */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return '需要扩展管理凭证：前后端的 PRIVILEGED_API_TOKEN 必须一致，改后需重启后端。';
  }
  return error instanceof Error ? error.message : '操作失败';
}

export function McpSettings() {
  const { data, isLoading, error } = useMcpServers();
  const upsert = useUpsertMcpServer();
  const remove = useDeleteMcpServer();
  const reconnect = useReconnectMcpServer();
  const [adding, setAdding] = useState(false);

  const servers = data?.servers ?? [];
  const mutationError = upsert.error ?? remove.error ?? reconnect.error;

  return (
    <section>
      <h3 className="hud-label mb-[2px] mt-[14px] text-text-tertiary">MCP 服务器</h3>
      <p className="mb-[10px] text-[11.5px] leading-[1.55] text-text-tertiary">
        通过 stdio 接入的 MCP 工具会注册为 <code className="font-mono">mcp__服务器__工具</code>。
        运行时无从判断远端工具会触及什么，因此每次调用都需人工审批。
      </p>

      {mutationError && (
        <p role="alert" className="mb-[10px] text-[11.5px] text-status-danger">
          {errorMessage(mutationError)}
        </p>
      )}

      {isLoading && <p className="py-[10px] text-[12px] text-text-tertiary">加载中…</p>}
      {error && (
        <p role="alert" className="py-[10px] text-[12px] text-status-danger">
          {errorMessage(error)}
        </p>
      )}

      {!isLoading && !error && servers.length === 0 && !adding && (
        <p className="py-[10px] text-[12px] text-text-tertiary">尚未配置任何 MCP 服务器。</p>
      )}

      <ul className="m-0 list-none p-0">
        {servers.map((server) => (
          <ServerRow
            key={server.name}
            server={server}
            busy={remove.isPending || reconnect.isPending}
            onReconnect={() => reconnect.mutate(server.name)}
            onDelete={() => remove.mutate(server.name)}
          />
        ))}
      </ul>

      {adding ? (
        <ServerForm
          busy={upsert.isPending}
          onCancel={() => setAdding(false)}
          onSubmit={(input) =>
            upsert.mutate(input, { onSuccess: () => setAdding(false) })
          }
        />
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="mt-[10px] flex items-center gap-[6px] rounded-md border border-border-subtle px-[10px] py-[6px] text-[11.5px] text-text-secondary transition-colors duration-fast hover:border-accent hover:text-accent"
        >
          <Plus size={13} />
          添加服务器
        </button>
      )}
    </section>
  );
}

function ServerRow({
  server,
  busy,
  onReconnect,
  onDelete,
}: {
  server: McpServer;
  busy: boolean;
  onReconnect: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="border-b border-border-subtle py-[9px] last:border-b-0">
      <div className="flex items-center gap-[10px]">
        <Plug size={13} className="flex-none text-text-tertiary" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-[8px]">
            <span className="text-body-sm font-medium text-text-primary">{server.name}</span>
            <span className={`font-mono text-[10px] ${STATUS_CLASS[server.status]}`}>
              {STATUS_LABEL[server.status]}
            </span>
          </div>
          <div className="mt-px truncate font-mono text-[10.5px] text-text-tertiary">
            {server.command} {server.args.join(' ')}
          </div>
        </div>
        <button
          type="button"
          aria-label={`重连 ${server.name}`}
          title="重连"
          disabled={busy}
          onClick={onReconnect}
          className="grid h-[24px] w-[24px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast hover:bg-surface-3 hover:text-accent disabled:opacity-50"
        >
          <RefreshCw size={13} />
        </button>
        <button
          type="button"
          aria-label={`删除 ${server.name}`}
          title="删除"
          disabled={busy}
          onClick={onDelete}
          className="grid h-[24px] w-[24px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast hover:bg-surface-3 hover:text-status-danger disabled:opacity-50"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {server.error && (
        <p className="mt-[6px] flex items-start gap-[6px] text-[11px] leading-[1.5] text-status-danger">
          <TriangleAlert size={12} className="mt-[2px] flex-none" />
          <span className="min-w-0 break-words">{server.error}</span>
        </p>
      )}

      {server.tools.length > 0 && (
        <ul className="m-0 mt-[6px] flex list-none flex-wrap gap-[6px] p-0">
          {server.tools.map((tool) => (
            <li
              key={tool.capability}
              title={tool.description || tool.capability}
              className="rounded-sm bg-surface-3 px-[6px] py-[2px] font-mono text-[10px] text-text-secondary"
            >
              {tool.name}
            </li>
          ))}
        </ul>
      )}

      {server.env_keys.length > 0 && (
        <p className="mt-[6px] font-mono text-[10px] text-text-tertiary">
          env: {server.env_keys.join(', ')}
        </p>
      )}
    </li>
  );
}

function ServerForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  onSubmit: (input: {
    name: string;
    command: string;
    args: string[];
    env: Record<string, string>;
    enabled: boolean;
  }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [command, setCommand] = useState('');
  const [args, setArgs] = useState('');

  const valid = /^[A-Za-z0-9._-]+$/.test(name) && command.trim().length > 0;

  return (
    <form
      className="mt-[10px] rounded-md border border-border-subtle p-[10px]"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onSubmit({
          name,
          command: command.trim(),
          // Whitespace-separated, which covers the `npx -y pkg` shape people paste.
          args: args.split(/\s+/).filter(Boolean),
          env: {},
          enabled: true,
        });
      }}
    >
      <label className="mb-[8px] block">
        <span className="hud-label text-text-tertiary">名称</span>
        <input
          aria-label="服务器名称"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="filesystem"
          className="mt-[3px] h-[26px] w-full rounded-md border border-border-subtle bg-surface-2 px-[8px] text-[11px] outline-none focus:border-accent"
        />
      </label>
      <label className="mb-[8px] block">
        <span className="hud-label text-text-tertiary">启动命令</span>
        <input
          aria-label="启动命令"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="npx"
          className="mt-[3px] h-[26px] w-full rounded-md border border-border-subtle bg-surface-2 px-[8px] font-mono text-[11px] outline-none focus:border-accent"
        />
      </label>
      <label className="block">
        <span className="hud-label text-text-tertiary">参数（空格分隔）</span>
        <input
          aria-label="启动参数"
          value={args}
          onChange={(event) => setArgs(event.target.value)}
          placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
          className="mt-[3px] h-[26px] w-full rounded-md border border-border-subtle bg-surface-2 px-[8px] font-mono text-[11px] outline-none focus:border-accent"
        />
      </label>
      <p className="mt-[8px] text-[10.5px] leading-[1.5] text-text-tertiary">
        子进程只继承 PATH/LANG/LC_ALL/TZ/HOME/TMPDIR，宿主的模型密钥不会传给 MCP 服务器。
      </p>
      <div className="mt-[10px] flex items-center gap-[8px]">
        <button
          type="submit"
          disabled={!valid || busy}
          className="rounded-md bg-accent px-[12px] py-[5px] text-[11.5px] text-surface-1 transition-opacity duration-fast disabled:opacity-50"
        >
          {busy ? '连接中…' : '保存并连接'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-border-subtle px-[12px] py-[5px] text-[11.5px] text-text-secondary transition-colors duration-fast hover:text-text-primary"
        >
          取消
        </button>
      </div>
    </form>
  );
}
