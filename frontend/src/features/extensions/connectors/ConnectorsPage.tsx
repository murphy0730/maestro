import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plug, SearchX } from 'lucide-react';
import {
  useDeleteMcpServer,
  useMcpServers,
  useReconnectMcpServer,
  useUpsertMcpServer,
} from '@/api';
import type { McpServer } from '@/types';
import { ExtensionSubTabs, type SubTab } from '../ExtensionSubTabs';
import { ConfirmDialog } from '../ConfirmDialog';
import { EmptyState, primaryButton } from '../shared';
import { errorMessage } from '../errors';
import { CatalogGrid } from '../catalog/CatalogGrid';
import {
  CATALOG_CONNECTORS,
  catalogEnabled,
  type CatalogConnector,
} from '../catalog/staticCatalog';
import { ConnectorListRow } from './ConnectorListRow';
import { ConnectorDetailDrawer } from './ConnectorDetailDrawer';
import { ConnectorEditorDrawer } from './ConnectorEditorDrawer';
import { connectorMatchesQuery } from './connectorFilter';

/**
 * 连接器域：已配置列表走真实的 `/mcp/servers` CRUD + 重连。
 * 「可用连接器」是本地静态模板，只预填表单，不代表远端目录。
 */
export function ConnectorsPage() {
  const [params, setParams] = useSearchParams();
  const serversQuery = useMcpServers();
  const upsert = useUpsertMcpServer();
  const remove = useDeleteMcpServer();
  const reconnect = useReconnectMcpServer();
  const [pendingDelete, setPendingDelete] = useState<McpServer>();
  const [editing, setEditing] = useState<McpServer>();
  const [template, setTemplate] = useState<CatalogConnector>();

  const servers = serversQuery.data?.servers ?? [];
  const query = params.get('q') ?? '';
  const browsable = catalogEnabled();
  const tab = params.get('tab') ?? (browsable ? 'recommended' : 'configured');
  const creating = params.get('new') === '1';
  const selected = servers.find((server) => server.name === params.get('connector'));

  const tabs: SubTab[] = browsable
    ? [
        { key: 'recommended', label: '推荐' },
        { key: 'catalog', label: '可用连接器' },
        { key: 'configured', label: '已配置', count: servers.length },
      ]
    : [{ key: 'configured', label: '已配置', count: servers.length }];

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const closeEditor = () => {
    setEditing(undefined);
    setTemplate(undefined);
    setParam('new', null);
  };

  const visible = servers.filter((server) => connectorMatchesQuery(server, query));
  const listError = serversQuery.error;
  const mutationError = remove.error ?? reconnect.error;
  const busy = remove.isPending || reconnect.isPending;
  const editorOpen = creating || Boolean(editing) || Boolean(template);

  return (
    <>
      <ExtensionSubTabs
        tabs={tabs}
        active={tab}
        label="连接器视图"
        onChange={(key) => setParam('tab', key)}
      />

      {mutationError && (
        <p
          role="alert"
          className="mb-[12px] rounded-md bg-status-error-bg p-[12px] text-[12px] text-status-error"
        >
          {errorMessage(mutationError)}
        </p>
      )}

      {tab === 'configured' ? (
        <>
          <div aria-live="polite">
            {serversQuery.isLoading && (
              <p className="py-[40px] text-center text-[12px] text-text-tertiary">
                正在加载连接器…
              </p>
            )}
            {listError && (
              <p role="alert" className="py-[40px] text-center text-[12px] text-status-error">
                {errorMessage(listError)}
              </p>
            )}
          </div>

          {!serversQuery.isLoading && !listError && (
            <div className="border-t border-border-subtle">
              {visible.map((server) => (
                <ConnectorListRow
                  key={server.name}
                  server={server}
                  busy={busy}
                  reconnecting={reconnect.isPending && reconnect.variables === server.name}
                  onOpen={() => setParam('connector', server.name)}
                  onEdit={() => setEditing(server)}
                  onReconnect={() => reconnect.mutate(server.name)}
                  onDelete={() => setPendingDelete(server)}
                />
              ))}
              {visible.length === 0 &&
                (servers.length === 0 ? (
                  <EmptyState
                    icon={<Plug size={34} />}
                    title="还没有配置连接器"
                    description="连接器把 MES / ERP / 排产引擎等外部系统通过 MCP 协议接入 Runtime。新增工具默认高风险，本机管理员可显式授予只读信任。"
                    action={
                      <button
                        type="button"
                        onClick={() => setParam('new', '1')}
                        className={`${primaryButton} mt-[8px]`}
                      >
                        添加连接器
                      </button>
                    }
                  />
                ) : (
                  <EmptyState
                    icon={<SearchX size={34} />}
                    title="没有匹配的连接器"
                    description="换个关键词试试。"
                  />
                ))}
            </div>
          )}
        </>
      ) : (
        <>
          <CatalogGrid
            emptyTitle="没有匹配的连接器"
            onOpen={(key) => setTemplate(CATALOG_CONNECTORS.find((item) => item.id === key))}
            items={CATALOG_CONNECTORS.filter(
              (item) =>
                !query ||
                `${item.name}${item.description}${item.id}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
            ).map((item) => ({
              key: item.id,
              title: item.name,
              subtitle: `${item.publisher} · stdio`,
              description: item.description,
              tags: [item.command, `${item.env_keys.length} 个环境变量`],
              installed: servers.some((server) => server.name === item.id),
            }))}
          />
          <p className="mt-[14px] text-[10.5px] leading-[1.6] text-text-tertiary">
            这是本地静态模板，只保存命令 / 参数 /
            环境变量名，不含任何密钥；选中只会预填表单，不会自动执行。
          </p>
        </>
      )}

      {editorOpen && (
        <ConnectorEditorDrawer
          key={editing?.name ?? template?.id ?? 'new'}
          server={editing}
          template={template}
          busy={upsert.isPending}
          error={upsert.error ? errorMessage(upsert.error) : undefined}
          onClose={closeEditor}
          onSubmit={(input) => upsert.mutate(input, { onSuccess: closeEditor })}
        />
      )}

      {selected && !editorOpen && (
        <ConnectorDetailDrawer
          server={selected}
          busy={busy}
          onClose={() => setParam('connector', null)}
          onEdit={() => {
            setParam('connector', null);
            setEditing(selected);
          }}
          onReconnect={() => reconnect.mutate(selected.name)}
          onDelete={() => setPendingDelete(selected)}
        />
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="删除连接器"
        confirmLabel="删除连接器"
        busy={remove.isPending}
        onCancel={() => setPendingDelete(undefined)}
        onConfirm={() => {
          const target = pendingDelete;
          if (!target) return;
          remove.mutate(target.name, {
            onSuccess: () => {
              setPendingDelete(undefined);
              if (params.get('connector') === target.name) setParam('connector', null);
            },
          });
        }}
      >
        将断开并删除 <span className="font-mono text-text-primary">{pendingDelete?.name}</span>
        ，它注册的 {pendingDelete?.tools.length ?? 0}{' '}
        个工具会立即从工具池移除，正在进行的调用会以连接错误失败。此操作不可撤销。
      </ConfirmDialog>
    </>
  );
}
