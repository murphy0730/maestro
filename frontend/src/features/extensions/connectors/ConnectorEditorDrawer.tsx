import { useState } from 'react';
import { Plus, TerminalSquare, TriangleAlert, X } from 'lucide-react';
import type { McpServer, McpServerInput } from '@/types';
import { DrawerSection, ExtensionDrawer } from '../ExtensionDrawer';
import { fieldInput, ghostButton, primaryButton } from '../shared';
import type { CatalogConnector } from '../catalog/staticCatalog';

interface EnvRow {
  key: string;
  value: string;
  secret: boolean;
  /** 服务端已存有此键，但取值不回显 —— 必须重新填写才能保住。 */
  carried: boolean;
}

const NAME_PATTERN = /^[A-Za-z0-9._-]+$/;

function initialEnv(server?: McpServer, template?: CatalogConnector): EnvRow[] {
  if (server)
    return server.env_keys.map((key) => ({ key, value: '', secret: true, carried: true }));
  if (template)
    return template.env_keys.map((key) => ({ key, value: '', secret: false, carried: false }));
  return [];
}

/**
 * 连接器编辑抽屉。后端 `PUT /mcp/servers/{name}` 是整体覆盖且从不回显 env 取值，
 * 所以编辑既有服务器时把已有键列出来标为「需重新填写」，并把覆盖语义说清楚，
 * 不假装能保留旧值。
 */
export function ConnectorEditorDrawer({
  server,
  template,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  server?: McpServer;
  template?: CatalogConnector;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (input: McpServerInput) => void;
}) {
  const [name, setName] = useState(server?.name ?? template?.id ?? '');
  const [command, setCommand] = useState(server?.command ?? template?.command ?? '');
  const [args, setArgs] = useState((server?.args ?? template?.args ?? []).join('\n'));
  const [env, setEnv] = useState<EnvRow[]>(() => initialEnv(server, template));

  const nameValid = NAME_PATTERN.test(name);
  const valid = nameValid && command.trim().length > 0 && !busy;
  const carriedSecrets = env.filter((row) => row.carried && !row.value.trim());

  const submit = (enabled: boolean) => {
    if (!valid) return;
    onSubmit({
      name,
      command: command.trim(),
      args: args
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
      env: Object.fromEntries(
        env.filter((row) => row.key.trim()).map((row) => [row.key.trim(), row.value]),
      ),
      enabled,
    });
  };

  const patch = (index: number, changes: Partial<EnvRow>) =>
    setEnv((rows) => rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));

  return (
    <ExtensionDrawer
      open
      onClose={onClose}
      title={server ? '编辑连接器' : '添加连接器'}
      subtitle={template ? `使用模板 · ${template.name}` : 'stdio · 本地进程'}
      footer={
        <>
          <button
            type="button"
            disabled={!valid}
            onClick={() => submit(false)}
            className={ghostButton}
          >
            保存但不连接
          </button>
          <span className="flex-1" />
          <button
            type="button"
            disabled={!valid}
            onClick={() => submit(true)}
            className={primaryButton}
          >
            {busy ? '连接中…' : '保存并连接'}
          </button>
        </>
      }
    >
      <DrawerSection title="基本信息">
        <label className="mb-[12px] block">
          <span className="mb-[5px] block text-[11.5px] text-text-secondary">
            唯一名称 <span className="text-status-error">*</span>
          </span>
          <input
            aria-label="服务器名称"
            value={name}
            disabled={Boolean(server)}
            onChange={(event) => setName(event.target.value)}
            placeholder="maestro-mes"
            className={`${fieldInput} font-mono disabled:opacity-60`}
          />
          <span className="mt-[4px] block text-[10.5px] text-text-tertiary">
            {server
              ? '名称是配置主键，保存后不可修改。'
              : '字母 / 数字 / . _ -；工具会注册为 mcp__名称__工具。'}
          </span>
        </label>
      </DrawerSection>

      <DrawerSection title="连接方式">
        <div className="flex items-center justify-center gap-[7px] rounded-md border border-accent-border bg-accent-bg px-[12px] py-[8px] text-[12px] text-accent">
          <TerminalSquare size={13} />
          本地进程（stdio）
        </div>
        <p className="mt-[6px] text-[10.5px] leading-[1.6] text-text-tertiary">
          SSE / HTTP 传输尚未实现；后端始终以 argv 启动子进程，不经 shell。
        </p>
      </DrawerSection>

      <DrawerSection title="进程配置">
        <label className="mb-[12px] block">
          <span className="mb-[5px] block text-[11.5px] text-text-secondary">
            Command <span className="text-status-error">*</span>
          </span>
          <input
            aria-label="启动命令"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            placeholder="python / node / 可执行文件绝对路径"
            className={`${fieldInput} font-mono`}
          />
        </label>
        <label className="mb-[12px] block">
          <span className="mb-[5px] block text-[11.5px] text-text-secondary">Args（每行一个）</span>
          <textarea
            aria-label="启动参数"
            value={args}
            onChange={(event) => setArgs(event.target.value)}
            rows={3}
            placeholder={'-y\n@modelcontextprotocol/server-filesystem\n/tmp'}
            className={`${fieldInput} min-h-[56px] resize-y font-mono text-[11.5px]`}
          />
        </label>

        <span className="mb-[5px] block text-[11.5px] text-text-secondary">环境变量</span>
        <div className="overflow-hidden rounded-md border border-border-subtle">
          <div className="grid grid-cols-[1fr_1fr_54px_28px] items-center gap-[8px] border-b border-border-subtle bg-surface-2 px-[10px] py-[7px]">
            <span className="hud-label text-text-tertiary">Key</span>
            <span className="hud-label text-text-tertiary">Value</span>
            <span className="hud-label text-text-tertiary">Secret</span>
            <span />
          </div>
          {env.map((row, index) => (
            <div
              key={index}
              className="grid grid-cols-[1fr_1fr_54px_28px] items-center gap-[8px] border-b border-border-subtle px-[10px] py-[7px] last:border-b-0"
            >
              <input
                aria-label={`环境变量名 ${index + 1}`}
                value={row.key}
                onChange={(event) => patch(index, { key: event.target.value })}
                placeholder="KEY"
                className="w-full border-b border-dashed border-transparent bg-transparent py-[2px] font-mono text-[11.5px] text-text-primary outline-none focus:border-accent placeholder:text-text-tertiary"
              />
              <input
                aria-label={`环境变量值 ${row.key || index + 1}`}
                value={row.value}
                type={row.secret ? 'password' : 'text'}
                onChange={(event) => patch(index, { value: event.target.value })}
                placeholder={row.carried ? '需重新填写' : 'value'}
                className={`w-full border-b border-dashed border-transparent bg-transparent py-[2px] font-mono text-[11.5px] text-text-primary outline-none focus:border-accent ${
                  row.carried && !row.value ? 'placeholder:text-status-warning' : 'placeholder:text-text-tertiary'
                }`}
              />
              <label className="flex cursor-pointer select-none items-center gap-[4px] text-[10.5px] text-text-tertiary">
                <input
                  type="checkbox"
                  aria-label={`将 ${row.key || `变量 ${index + 1}`} 视为密钥`}
                  checked={row.secret}
                  onChange={(event) => patch(index, { secret: event.target.checked })}
                  className="accent-[var(--accent)]"
                />
                密
              </label>
              <button
                type="button"
                aria-label={`删除环境变量 ${row.key || index + 1}`}
                onClick={() => setEnv((rows) => rows.filter((_, i) => i !== index))}
                className="grid h-[22px] w-[22px] place-items-center rounded-sm text-text-tertiary transition-colors hover:bg-surface-3 hover:text-status-error"
              >
                <X size={12} />
              </button>
            </div>
          ))}
          {env.length === 0 && (
            <p className="m-0 px-[10px] py-[9px] text-[11px] text-text-tertiary">
              没有环境变量。
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() =>
            setEnv((rows) => [...rows, { key: '', value: '', secret: false, carried: false }])
          }
          className={`${ghostButton} mt-[8px] px-[10px] py-[4px] text-[11.5px]`}
        >
          <Plus size={12} />
          添加变量
        </button>

        {carriedSecrets.length > 0 && (
          <p className="mt-[8px] flex items-start gap-[8px] text-[11px] leading-[1.6] text-status-warning">
            <TriangleAlert size={13} className="mt-[2px] flex-none" />
            后端不回显环境变量取值，保存会整体覆盖：
            <span className="font-mono">{carriedSecrets.map((row) => row.key).join('、')}</span>{' '}
            未重新填写，将被写为空值。
          </p>
        )}
        <p className="mt-[8px] text-[10.5px] leading-[1.6] text-text-tertiary">
          子进程只继承 PATH / LANG / LC_ALL / TZ / HOME / TMPDIR 与这里配置的变量。
        </p>
      </DrawerSection>

      {!nameValid && name.length > 0 && (
        <p role="alert" className="text-[11.5px] text-status-error">
          名称只能包含字母、数字与 . _ -
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-md bg-status-error-bg p-[12px] text-[12px] text-status-error"
        >
          {error}
        </p>
      )}
    </ExtensionDrawer>
  );
}
