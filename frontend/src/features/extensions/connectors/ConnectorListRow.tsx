import { Badge } from '@/components/ui/Badge';
import type { McpServer } from '@/types';
import { ExtensionIcon, dangerRowButton, rowButton } from '../shared';
import { ConnectorStatusBadge } from './connectorStatus';

export function ConnectorListRow({
  server,
  busy,
  reconnecting,
  onOpen,
  onEdit,
  onReconnect,
  onDelete,
}: {
  server: McpServer;
  busy: boolean;
  reconnecting: boolean;
  onOpen: () => void;
  onEdit: () => void;
  onReconnect: () => void;
  onDelete: () => void;
}) {
  // 后端目前不返回 managed；一旦返回，托管配置在这里就是只读的。
  const managed = server.managed === true;
  return (
    <div className="flex items-center gap-[14px] border-b border-border-subtle px-[10px] py-[12px] transition-colors duration-fast hover:bg-surface-3">
      <ExtensionIcon name={server.name} />
      <button
        type="button"
        onClick={onOpen}
        className="min-w-0 flex-1 text-left"
        aria-label={`查看连接器 ${server.name} 详情`}
      >
        <span className="flex items-center gap-[8px] text-[13px] font-semibold text-text-primary">
          <span className="truncate">{server.name}</span>
          {managed && <Badge tone="controlled">由环境管理</Badge>}
        </span>
        <span className="block truncate font-mono text-[11px] text-text-tertiary">
          {server.command} {server.args.join(' ')}
        </span>
      </button>
      <span className="w-[52px] flex-none font-mono text-[11px] text-text-secondary max-lg:hidden">
        stdio
      </span>
      <span className="w-[104px] flex-none max-md:hidden">
        <ConnectorStatusBadge server={server} />
      </span>
      <span className="w-[70px] flex-none font-mono text-[11px] text-text-secondary max-lg:hidden">
        {server.tools.length} 工具
      </span>
      <span className="flex flex-none items-center gap-[6px]">
        <button type="button" disabled={busy} onClick={onReconnect} className={rowButton}>
          {reconnecting ? '重连中…' : '重连'}
        </button>
        <button type="button" onClick={onOpen} className={rowButton}>
          详情
        </button>
        <button
          type="button"
          disabled={managed}
          title={managed ? '由环境管理，界面不可编辑' : undefined}
          onClick={onEdit}
          aria-label={`编辑连接器 ${server.name}`}
          className={rowButton}
        >
          编辑
        </button>
        <button
          type="button"
          disabled={busy || managed}
          title={managed ? '由环境管理，界面不可删除' : undefined}
          onClick={onDelete}
          aria-label={`删除连接器 ${server.name}`}
          className={dangerRowButton}
        >
          删除
        </button>
      </span>
    </div>
  );
}
