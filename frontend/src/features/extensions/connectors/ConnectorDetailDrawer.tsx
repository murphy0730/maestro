import { CircleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import type { McpServer } from '@/types';
import { DrawerKeyValues, DrawerSection, ExtensionDrawer } from '../ExtensionDrawer';
import { dangerButton, ghostButton, primaryButton } from '../shared';
import { ConnectorStatusBadge } from './connectorStatus';

export function ConnectorDetailDrawer({
  server,
  busy,
  onClose,
  onEdit,
  onReconnect,
  onDelete,
}: {
  server: McpServer;
  busy: boolean;
  onClose: () => void;
  onEdit: () => void;
  onReconnect: () => void;
  onDelete: () => void;
}) {
  const managed = server.managed === true;
  return (
    <ExtensionDrawer
      open
      onClose={onClose}
      title={server.name}
      header={<ConnectorStatusBadge server={server} />}
      subtitle="stdio · 本地子进程"
      footer={
        <>
          <button type="button" disabled={busy} onClick={onReconnect} className={primaryButton}>
            重新连接
          </button>
          <span className="flex-1" />
          {!managed && (
            <>
              <button type="button" onClick={onEdit} className={ghostButton}>
                编辑
              </button>
              <button type="button" disabled={busy} onClick={onDelete} className={dangerButton}>
                删除连接器
              </button>
            </>
          )}
        </>
      }
    >
      <DrawerSection title="概览">
        <DrawerKeyValues
          rows={[
            ['状态', <ConnectorStatusBadge key="status" server={server} />],
            ['传输', 'stdio（本地子进程）'],
            ['启用', server.enabled ? '是' : '否'],
            ['已发布工具', `${server.tools.length} 个`],
          ]}
        />
        {server.error && (
          <p className="m-0 mt-[8px] flex items-start gap-[8px] text-[11.5px] leading-[1.6] text-status-error">
            <CircleAlert size={13} className="mt-[2px] flex-none" />
            <span className="min-w-0 break-words">{server.error}</span>
          </p>
        )}
      </DrawerSection>

      {server.tools.length > 0 && (
        <DrawerSection title="工具">
          {server.tools.map((tool) => (
            <div
              key={tool.capability}
              className="border-b border-dashed border-border-subtle py-[7px] last:border-b-0"
            >
              <Badge tone="planning">{tool.name}</Badge>
              <p className="m-0 mt-[4px] text-[11.5px] leading-[1.6] text-text-secondary">
                {tool.description || '远端未提供描述'}
              </p>
              <p className="m-0 font-mono text-[10px] text-text-tertiary">{tool.capability}</p>
            </div>
          ))}
          <p className="mt-[6px] text-[10.5px] leading-[1.6] text-text-tertiary">
            这里不提供直接调用入口；工具只在对话中经 Policy Gate 审批后执行。
          </p>
        </DrawerSection>
      )}

      <DrawerSection title="安全说明">
        <p className="m-0 text-[12.5px] leading-[1.7] text-text-secondary">
          Runtime 无从判断远端工具会触及什么，因此所有 MCP 工具一律按高风险写操作处理，每次调用都需人工确认。
          子进程只继承 PATH / LANG / LC_ALL / TZ / HOME / TMPDIR 与此处配置的环境变量，宿主的模型密钥不会传给它。
        </p>
      </DrawerSection>

      <DrawerSection title="配置（已脱敏）">
        <DrawerKeyValues
          rows={[
            ['command', server.command],
            ['args', server.args.join(' ') || '—'],
            ['env', server.env_keys.join('、') || '—'],
          ]}
        />
        <p className="mt-[6px] text-[10.5px] leading-[1.6] text-text-tertiary">
          后端只回传环境变量名，永不回显取值。
        </p>
      </DrawerSection>

      {managed && (
        <DrawerSection title="托管来源">
          <p className="m-0 text-[12.5px] leading-[1.7] text-text-secondary">
            该配置由环境管理，界面只能查看脱敏信息与状态。
          </p>
        </DrawerSection>
      )}
    </ExtensionDrawer>
  );
}
