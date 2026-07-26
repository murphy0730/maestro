import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import type { McpServer } from '@/types';

/**
 * 连接器状态：颜色之外始终带文字与状态点，不靠颜色单独传达。
 * `disconnected` 有两种含义 —— 停用与未连接，`enabled` 才能区分。
 */
export function ConnectorStatusBadge({ server }: { server: McpServer }) {
  if (server.status === 'connected')
    return (
      <Badge tone="success" icon={<StatusDot tone="success" />}>
        已连接
      </Badge>
    );
  if (server.status === 'error')
    return (
      <Badge tone="danger" icon={<StatusDot tone="danger" />}>
        连接失败
      </Badge>
    );
  return (
    <Badge icon={<StatusDot tone="muted" />}>{server.enabled ? '未连接' : '已停用'}</Badge>
  );
}
