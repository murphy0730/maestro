import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Cable,
  ChevronRight,
  Download,
  PlugZap,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Sidebar } from '@/components/layout/Sidebar';
import { Modal } from '@/components/ui/Modal';
import { SkillImportModal } from '@/features/orchestrator/skills/SkillImportModal';
import {
  connectConnector,
  createConnector,
  deleteConnector,
  disconnectConnector,
  getCatalogStatus,
  installCatalogSkill,
  listCatalogConnectors,
  listCatalogSkills,
  addCatalogConnector,
  previewCatalogConnectorUpdate,
  syncCatalog,
  updateCatalogConnector,
  listConnectors,
  queryKeys,
  useDeleteSkill,
  useSkills,
  useTrustSkill,
} from '@/api';
import type {
  CatalogConnector,
  CatalogSkill,
  ConnectorInput,
  ConnectorServer,
  SkillMeta,
} from '@/types';
import { useDefaultEngineStore, useThemeStore } from '@/stores';
import { useWorkspaceSessions } from '@/pages/workspace/useWorkspaceSessions';

const CARD_DESCRIPTION_LIMIT = 50;

function cardDescription(description: string) {
  const characters = Array.from(description.trim());
  if (characters.length <= CARD_DESCRIPTION_LIMIT) return characters.join('');
  return `${characters.slice(0, CARD_DESCRIPTION_LIMIT - 1).join('')}…`;
}

function ExtensionSidebar() {
  const navigate = useNavigate();
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const defaultEngine = useDefaultEngineStore((s) => s.defaultEngine);
  const setDefaultEngine = useDefaultEngineStore((s) => s.setDefaultEngine);
  const sessions = useWorkspaceSessions({ onFreshConversation: () => navigate('/') });
  return (
    <Sidebar
      appName="Maestro"
      user="周文涛"
      initial="Z"
      role="排产调度员"
      conversations={sessions.sidebarConversations}
      activeId={sessions.activeSessionId ?? ''}
      onSelect={(id) => {
        sessions.handleSelectSession(id);
        navigate('/');
      }}
      onNewConversation={() => {
        sessions.handleNewConversation();
        navigate('/');
      }}
      onOpenTasks={() => navigate('/tasks')}
      onOpenSkills={() => navigate('/settings/skills')}
      onOpenConnectors={() => navigate('/settings/connectors')}
      onRenameSession={sessions.handleRenameSession}
      onDeleteSession={sessions.handleDeleteSession}
      onCollapse={() => undefined}
      theme={theme}
      onSetTheme={setTheme}
      defaultEngine={defaultEngine}
      onSetDefaultEngine={setDefaultEngine}
    />
  );
}

function Header({
  kind,
  count,
  onPrimary,
}: {
  kind: 'skills' | 'connectors';
  count: number;
  onPrimary: () => void;
}) {
  const [params, setParams] = useSearchParams();
  return (
    <>
      <header className="flex h-header items-center border-b border-border-subtle px-7">
        <div>
          <h1 className="font-display text-h3 font-semibold text-text-primary">扩展中心</h1>
        </div>
        <nav className="ml-8 flex h-full items-end gap-6" aria-label="扩展类型">
          {(
            [
              ['skills', '技能'],
              ['connectors', '连接器'],
            ] as const
          ).map(([key, label]) => (
            <Link
              key={key}
              to={`/settings/${key}`}
              className={`relative flex h-full items-center text-body-sm font-medium ${kind === key ? 'text-text-primary' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {label}
              {kind === key && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-planning" />}
            </Link>
          ))}
        </nav>
        <label className="ml-auto flex h-control w-64 items-center gap-2 rounded-sm border border-border-default bg-surface-1 px-3 focus-within:border-planning">
          <Search size={14} className="text-text-tertiary" />
          <input
            value={params.get('q') ?? ''}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              e.target.value ? next.set('q', e.target.value) : next.delete('q');
              setParams(next, { replace: true });
            }}
            placeholder={`搜索${kind === 'skills' ? '技能' : '连接器'}`}
            className="min-w-0 flex-1 bg-transparent text-body-sm text-text-primary outline-none"
          />
        </label>
        <span className="ml-3 text-caption text-text-tertiary">
          已{kind === 'skills' ? '安装' : '配置'} {count}
        </span>
        <button
          onClick={onPrimary}
          className="ml-4 inline-flex h-control items-center gap-2 rounded-sm bg-blue-solid px-4 text-body-sm font-medium text-on-solid hover:bg-blue-solid-hover"
        >
          {kind === 'skills' ? <Download size={14} /> : <PlugZap size={14} />}{' '}
          {kind === 'skills' ? '导入技能' : '添加连接器'}
        </button>
      </header>
    </>
  );
}

function SkillsView() {
  const qc = useQueryClient();
  const { data, isLoading } = useSkills();
  const trust = useTrustSkill();
  const remove = useDeleteSkill();
  const [params] = useSearchParams();
  const [importOpen, setImportOpen] = useState(false);
  const [selected, setSelected] = useState<SkillMeta | null>(null);
  const [skillToRemove, setSkillToRemove] = useState<SkillMeta | null>(null);
  const [tab, setTab] = useState<'installed' | 'recommended' | 'hub'>('installed');
  const q = params.get('q') ?? '';
  const catalog = useQuery({
    queryKey: queryKeys.extensions.catalog('skills', q),
    queryFn: () => listCatalogSkills(q),
    enabled: tab !== 'installed',
  });
  const catalogStatus = useQuery({
    queryKey: queryKeys.extensions.catalogStatus(),
    queryFn: getCatalogStatus,
  });
  const sync = useMutation({
    mutationFn: () => syncCatalog(),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.extensions.catalogStatus() }),
  });
  const install = useMutation({
    mutationFn: (item: CatalogSkill) => installCatalogSkill(item),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.skills.list() });
      void qc.invalidateQueries({ queryKey: ['extensions', 'catalog'] });
    },
  });
  const skills = useMemo(() => {
    const q = (params.get('q') ?? '').toLowerCase();
    return (data?.skills ?? []).filter((s) =>
      `${s.name} ${s.display_name ?? ''} ${s.summary_zh ?? ''} ${s.description_zh ?? ''} ${s.description} ${s.author ?? ''}`
        .toLowerCase()
        .includes(q),
    );
  }, [data, params]);
  return (
    <>
      <Header
        kind="skills"
        count={data?.skills.length ?? 0}
        onPrimary={() => setImportOpen(true)}
      />
      <div className="animate-[fadeIn_180ms_ease-out] overflow-auto px-7 py-6">
        <div className="mb-4 flex items-center rounded-sm border border-border-subtle bg-surface-1 px-4 py-2 text-caption text-text-tertiary">
          <span>
            最后同步：
            {catalogStatus.data?.latest?.completed_at
              ? new Date(catalogStatus.data.latest.completed_at).toLocaleString()
              : '尚未同步'}
          </span>
          <button
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
            className="ml-auto text-planning hover:underline disabled:opacity-50"
          >
            {sync.isPending ? '同步中…' : '立即同步'}
          </button>
        </div>
        <div className="mb-5 flex gap-5 border-b border-border-subtle text-body-sm">
          {(
            [
              ['installed', '已安装'],
              ['recommended', '推荐'],
              ['hub', 'SkillHub'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`pb-3 ${tab === key ? 'border-b-2 border-planning font-medium text-text-primary' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>
        {tab !== 'installed' ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
            {(tab === 'recommended'
              ? (catalog.data?.items ?? []).filter((item) => item.installable).slice(0, 12)
              : (catalog.data?.items ?? [])
            ).map((item) => {
              const installed = item.installed;
              const isInstalling =
                install.isPending && install.variables?.catalog_id === item.catalog_id;
              return (
                <article
                  key={item.catalog_id}
                  className="flex min-h-40 flex-col rounded-md border border-border-subtle bg-surface-1 p-5 shadow-elev-1 transition-[border-color,transform] duration-150 hover:-translate-y-px hover:border-border-default"
                >
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-planning-bg text-planning">
                      <Sparkles size={17} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body font-medium text-text-primary">
                        {item.display_name}
                      </span>
                      <span
                        title={item.description_zh ?? item.description}
                        className="mt-1 block line-clamp-2 text-body-sm text-text-secondary"
                      >
                        {cardDescription(item.summary_zh ?? item.description)}
                      </span>
                    </span>
                  </div>
                  <div className="mt-auto flex items-center border-t border-border-subtle pt-4">
                    <span className="mr-3 text-caption text-planning-fg">{item.source_name}</span>
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-caption text-text-tertiary hover:text-text-secondary"
                    >
                      查看来源
                    </a>
                    <button
                      disabled={
                        (installed && !item.update_available) ||
                        !item.installable ||
                        install.isPending
                      }
                      onClick={() => install.mutate(item)}
                      className="ml-auto h-control rounded-sm border border-border-default px-4 text-body-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {!item.installable
                        ? '不可安装'
                        : item.update_available
                          ? '更新'
                          : installed
                            ? '已安装'
                            : isInstalling
                              ? '安装中…'
                              : '添加'}
                    </button>
                  </div>
                </article>
              );
            })}
            {install.error && (
              <p className="mt-4 text-body-sm text-status-error">{install.error.message}</p>
            )}
          </div>
        ) : isLoading ? (
          <p className="text-text-tertiary">加载技能…</p>
        ) : skills.length === 0 ? (
          <div className="py-24 text-center">
            <Sparkles className="mx-auto text-text-tertiary" />
            <h2 className="mt-4 text-h3 text-text-primary">暂无匹配技能</h2>
            <p className="mt-2 text-body-sm text-text-tertiary">
              导入 .md 或 .zip 技能包开始使用。
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
            {skills.map((skill) => (
              <article
                key={skill.name}
                onClick={() => setSelected(skill)}
                className="group flex min-h-40 cursor-pointer flex-col rounded-md border border-border-subtle bg-surface-1 p-5 text-left shadow-elev-1 transition-[border-color,transform] duration-150 hover:-translate-y-px hover:border-border-default focus-within:border-border-accent"
              >
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-planning-bg text-planning">
                    <Sparkles size={17} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-body font-medium text-text-primary">
                      {skill.display_name ?? skill.name}
                    </span>
                    <span
                      title={skill.description_zh ?? skill.description}
                      className="mt-1 block line-clamp-2 text-body-sm text-text-secondary"
                    >
                      {cardDescription(skill.summary_zh ?? skill.description)}
                    </span>
                  </span>
                  <ChevronRight
                    size={16}
                    className="mt-1 shrink-0 text-text-tertiary group-hover:text-text-secondary"
                  />
                </div>
                <div className="mt-auto flex items-center gap-2 border-t border-border-subtle pt-4 text-caption text-text-tertiary">
                  <span className="font-medium text-planning-fg">技能详情</span>
                  <span>·</span>
                  <span className="truncate">
                    {skill.author ?? '本地导入'} · {skill.version ?? '未标版本'}
                  </span>
                  <button
                    aria-label={`卸载 ${skill.display_name ?? skill.name}`}
                    title="卸载技能"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSkillToRemove(skill);
                    }}
                    className="ml-auto grid h-7 w-7 shrink-0 place-items-center rounded-sm text-text-tertiary hover:bg-status-error-bg hover:text-status-error"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
      {selected && (
        <aside className="absolute inset-y-0 right-0 z-20 flex w-[min(460px,52vw)] flex-col border-l border-border-subtle bg-surface-1 shadow-elev-3">
          <div className="flex items-start border-b border-border-subtle p-6">
            <div className="flex-1">
              <p className="text-caption text-text-tertiary">技能详情</p>
              <h2 className="mt-1 text-h2 font-semibold text-text-primary">
                {selected.display_name ?? selected.name}
              </h2>
            </div>
            <button aria-label="关闭详情" onClick={() => setSelected(null)}>
              <X size={18} />
            </button>
          </div>
          <div className="flex-1 overflow-auto p-6">
            <p className="text-body text-text-secondary">
              {selected.description_zh ?? selected.summary_zh ?? selected.description}
            </p>
            <h3 className="mt-7 text-body-sm font-semibold text-text-primary">工具与权限</h3>
            <p className="mt-2 text-body-sm text-text-secondary">
              {selected.allowed_tools?.join('、') || '只使用默认只读工具'}
            </p>
            <h3 className="mt-7 text-body-sm font-semibold text-text-primary">包信息</h3>
            <dl className="mt-2 grid grid-cols-2 gap-y-2 text-body-sm">
              <dt className="text-text-tertiary">文件</dt>
              <dd>{selected.file_count}</dd>
              <dt className="text-text-tertiary">解压大小</dt>
              <dd>{selected.bytes} bytes</dd>
              <dt className="text-text-tertiary">SHA-256</dt>
              <dd className="truncate font-mono text-caption">{selected.package_sha256}</dd>
              {selected.trust?.valid && selected.trust.trusted_at ? (
                <>
                  <dt className="text-text-tertiary">信任时间</dt>
                  <dd>{new Date(selected.trust.trusted_at).toLocaleString()}</dd>
                </>
              ) : null}
            </dl>
          </div>
          <div className="flex gap-3 border-t border-border-subtle p-4">
            {selected.scripts?.length && !selected.trust?.valid ? (
              <button
                disabled={trust.isPending}
                onClick={() =>
                  trust.mutate(
                    { name: selected.name, packageSha256: selected.package_sha256 },
                    {
                      onSuccess: (trustStatus) =>
                        setSelected((current) =>
                          current?.name === selected.name
                            ? { ...current, trust: trustStatus }
                            : current,
                        ),
                    },
                  )
                }
                className="h-control rounded-sm bg-blue-solid px-4 text-body-sm text-on-solid disabled:opacity-50"
              >
                <ShieldCheck size={14} className="mr-2 inline" />
                {trust.isPending ? '正在信任…' : '信任当前版本'}
              </button>
            ) : null}
            {selected.scripts?.length && selected.trust?.valid ? (
              <div className="flex min-w-0 items-center gap-2 text-body-sm text-status-success">
                <ShieldCheck size={15} className="shrink-0" />
                <span className="font-medium">已信任该技能版本</span>
              </div>
            ) : null}
            <button
              onClick={() => setSkillToRemove(selected)}
              className="ml-auto h-control rounded-sm px-4 text-body-sm text-status-error hover:bg-status-error-soft"
            >
              卸载技能
            </button>
          </div>
        </aside>
      )}
      <SkillImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => setImportOpen(false)}
      />
      <Modal
        open={skillToRemove !== null}
        onClose={() => {
          if (!remove.isPending) setSkillToRemove(null);
        }}
        title="卸载技能"
        subtitle="此操作不会删除由该技能生成的历史内容。"
        footer={
          <>
            <button
              disabled={remove.isPending}
              onClick={() => setSkillToRemove(null)}
              className="ml-auto h-control rounded-sm border border-border-default px-4 text-body-sm font-medium text-text-secondary hover:bg-surface-1 disabled:opacity-50"
            >
              取消
            </button>
            <button
              disabled={remove.isPending}
              onClick={() => {
                if (!skillToRemove) return;
                const name = skillToRemove.name;
                remove.mutate(name, {
                  onSuccess: () => {
                    setSkillToRemove(null);
                    if (selected?.name === name) setSelected(null);
                  },
                });
              }}
              className="h-control rounded-sm bg-status-error px-4 text-body-sm font-medium text-on-solid hover:opacity-90 disabled:opacity-50"
            >
              {remove.isPending ? '卸载中…' : '确认卸载'}
            </button>
          </>
        }
      >
        <p className="text-body-sm leading-relaxed text-text-secondary">
          确定要卸载技能
          <span className="font-medium text-text-primary">
            「{skillToRemove?.display_name ?? skillToRemove?.name}」
          </span>
          吗？卸载后，该技能将无法在新对话中使用。
        </p>
        {remove.error && <p className="mt-3 text-body-sm text-status-error">卸载失败，请重试。</p>}
      </Modal>
    </>
  );
}

function ConnectorsView() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.extensions.connectors(),
    queryFn: listConnectors,
  });
  const [params] = useSearchParams();
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<ConnectorServer | null>(null);
  const [tab, setTab] = useState<'configured' | 'recommended' | 'available'>('configured');
  const q = (params.get('q') ?? '').toLowerCase();
  const catalog = useQuery({
    queryKey: queryKeys.extensions.catalog('connectors', q),
    queryFn: () => listCatalogConnectors(q),
    enabled: tab !== 'configured',
  });
  const form = useRef<ConnectorInput>({
    name: '',
    description: '',
    transport_type: 'stdio',
    command: '',
    args: [],
    env: {},
    secret_env_keys: [],
  });
  const mutate = useMutation({
    mutationFn: createConnector,
    onSuccess: () => {
      setEditing(false);
      void qc.invalidateQueries({ queryKey: queryKeys.extensions.connectors() });
    },
  });
  const addFromCatalog = useMutation({
    mutationFn: (item: CatalogConnector) => addCatalogConnector(item, data?.revision),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.extensions.connectors() });
      void qc.invalidateQueries({ queryKey: ['extensions', 'catalog'] });
    },
  });
  const updateFromCatalog = useMutation({
    mutationFn: async (item: CatalogConnector) => {
      const preview = await previewCatalogConnectorUpdate(item);
      const summary = Object.entries(preview.changes)
        .filter(([, change]) => JSON.stringify(change.before) !== JSON.stringify(change.after))
        .map(([field]) => field)
        .join('、');
      if (
        !confirm(
          `更新连接器模板${summary ? `（变化：${summary}）` : ''}？环境变量、密钥和启用状态会保留。`,
        )
      )
        return;
      return updateCatalogConnector(item, preview.revision, preview.catalog_template_sha256);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.extensions.connectors() });
      void qc.invalidateQueries({ queryKey: ['extensions', 'catalog'] });
    },
  });
  const toggle = useMutation({
    mutationFn: ({ s, enable }: { s: ConnectorServer; enable: boolean }) =>
      enable
        ? connectConnector(s.name, data?.revision ?? 0)
        : disconnectConnector(s.name, data?.revision ?? 0),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.extensions.connectors() }),
  });
  const remove = useMutation({
    mutationFn: (server: ConnectorServer) => deleteConnector(server.name, data?.revision ?? 0),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.extensions.connectors() }),
  });
  const servers = (data?.servers ?? []).filter((s) =>
    `${s.name} ${s.display_name ?? ''} ${s.description}`.toLowerCase().includes(q),
  );
  return (
    <>
      <Header
        kind="connectors"
        count={data?.servers.length ?? 0}
        onPrimary={() => setEditing(true)}
      />
      <div className="overflow-auto px-7 py-6">
        <div className="mb-5 flex gap-5 border-b border-border-subtle text-body-sm">
          {(
            [
              ['configured', '已配置'],
              ['recommended', '推荐'],
              ['available', '可用连接器'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`pb-3 ${tab === key ? 'border-b-2 border-planning font-medium text-text-primary' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>
        {tab !== 'configured' ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
            {(tab === 'recommended'
              ? (catalog.data?.items ?? []).filter((item) => item.installable).slice(0, 12)
              : (catalog.data?.items ?? [])
            ).map((item) => {
              const configured = item.configured;
              const isAdding =
                addFromCatalog.isPending &&
                addFromCatalog.variables?.catalog_id === item.catalog_id;
              const isUpdating =
                updateFromCatalog.isPending &&
                updateFromCatalog.variables?.catalog_id === item.catalog_id;
              return (
                <article
                  key={item.catalog_id}
                  className="flex min-h-40 flex-col rounded-md border border-border-subtle bg-surface-1 p-5 shadow-elev-1 transition-[border-color,transform] duration-150 hover:-translate-y-px hover:border-border-default"
                >
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-surface-3 text-text-secondary">
                      <Cable size={17} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body font-medium text-text-primary">
                        {item.display_name}
                      </span>
                      <span
                        title={item.description}
                        className="mt-1 block line-clamp-2 text-body-sm text-text-secondary"
                      >
                        {item.summary_zh ?? item.description}
                      </span>
                    </span>
                  </div>
                  <div className="mt-auto flex items-center border-t border-border-subtle pt-4">
                    <span className="mr-3 text-caption text-planning-fg">{item.source_name}</span>
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-caption text-text-tertiary hover:text-text-secondary"
                    >
                      查看来源
                    </a>
                    <button
                      disabled={
                        (configured && !item.update_available) ||
                        !item.installable ||
                        addFromCatalog.isPending ||
                        updateFromCatalog.isPending
                      }
                      onClick={() =>
                        item.update_available
                          ? updateFromCatalog.mutate(item)
                          : addFromCatalog.mutate(item)
                      }
                      className="ml-auto h-control rounded-sm border border-border-default px-4 text-body-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {!item.installable
                        ? '不可添加'
                        : item.update_available
                          ? '更新模板'
                          : configured
                            ? '已添加'
                            : isUpdating
                              ? '更新中…'
                              : isAdding
                                ? '添加中…'
                                : '添加'}
                    </button>
                  </div>
                </article>
              );
            })}
            {(addFromCatalog.error || updateFromCatalog.error) && (
              <p className="mt-4 text-body-sm text-status-error">
                {(addFromCatalog.error ?? updateFromCatalog.error)?.message}
              </p>
            )}
          </div>
        ) : isLoading ? (
          <p>加载连接器…</p>
        ) : servers.length === 0 ? (
          <div className="py-24 text-center">
            <Cable className="mx-auto text-text-tertiary" />
            <h2 className="mt-4 text-h3 text-text-primary">尚未配置连接器</h2>
            <p className="mt-2 text-body-sm text-text-tertiary">
              添加本地 stdio MCP Server，将工具接入 Maestro。
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
            {servers.map((s) => (
              <article
                key={s.name}
                onClick={() => setSelected(s)}
                className="group flex min-h-40 cursor-pointer flex-col rounded-md border border-border-subtle bg-surface-1 p-5 shadow-elev-1 transition-[border-color,transform] duration-150 hover:-translate-y-px hover:border-border-default"
              >
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-surface-3 text-text-secondary">
                    <Cable size={17} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-text-primary">
                      {s.display_name ?? s.name}
                    </p>
                    <p className="mt-1 line-clamp-2 text-body-sm text-text-secondary">
                      {s.description || s.command}
                    </p>
                  </div>
                  <ChevronRight
                    size={16}
                    className="mt-1 shrink-0 text-text-tertiary group-hover:text-text-secondary"
                  />
                </div>
                <div className="mt-auto flex items-center gap-2 border-t border-border-subtle pt-4">
                  <span
                    className={`text-caption ${s.status === 'connected' ? 'text-status-success' : 'text-text-tertiary'}`}
                  >
                    {s.managed ? '由环境管理' : s.status === 'connected' ? '已连接' : '未连接'}
                  </span>
                  {!s.managed && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggle.mutate({ s, enable: !s.enabled });
                      }}
                      className="ml-auto h-control rounded-sm border border-border-default px-3 text-body-sm hover:bg-surface-2"
                    >
                      {s.enabled ? '断开' : '连接'}
                    </button>
                  )}
                  {!s.managed && (
                    <button
                      aria-label={`删除 ${s.display_name ?? s.name}`}
                      title="删除连接器"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (confirm(`删除连接器「${s.display_name ?? s.name}」？`))
                          remove.mutate(s);
                      }}
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-sm text-text-tertiary hover:bg-status-error-bg hover:text-status-error"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
      {editing && (
        <aside className="absolute inset-y-0 right-0 z-20 flex w-[min(460px,100vw)] flex-col border-l border-border-subtle bg-surface-1 shadow-elev-3">
          <div className="flex items-center border-b border-border-subtle p-6">
            <h2 className="text-h2 font-semibold">添加连接器</h2>
            <button className="ml-auto" onClick={() => setEditing(false)}>
              <X />
            </button>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutate.mutate({ ...form.current, expected_revision: data?.revision });
            }}
            className="flex flex-1 flex-col overflow-auto p-6"
          >
            <p className="mb-6 rounded-sm bg-status-warning-soft p-3 text-caption text-status-warning">
              保存并连接会启动本地进程。Secret 当前以明文保存在本机 settings.json，但不会由 API
              回传。
            </p>
            {[
              ['显示名称', 'display_name'],
              ['唯一名称', 'name'],
              ['启动命令', 'command'],
            ].map(([label, key]) => (
              <label key={key} className="mb-5 text-body-sm text-text-secondary">
                {label}
                <input
                  required={key !== 'display_name'}
                  onChange={(e) => {
                    (form.current as unknown as Record<string, string>)[key] = e.target.value;
                  }}
                  className="mt-2 h-control w-full rounded-sm border border-border-default bg-bg-base px-3 text-text-primary outline-none focus:border-planning"
                />
              </label>
            ))}
            <label className="text-body-sm text-text-secondary">
              参数（每行一个）
              <textarea
                onChange={(e) => (form.current.args = e.target.value.split('\n').filter(Boolean))}
                className="mt-2 h-28 w-full rounded-sm border border-border-default bg-bg-base p-3 font-mono text-caption"
              />
            </label>
            <button
              disabled={mutate.isPending}
              className="mt-auto h-control rounded-sm bg-blue-solid text-body-sm font-medium text-on-solid"
            >
              {mutate.isPending ? '保存中…' : '仅保存'}
            </button>
          </form>
        </aside>
      )}
      {selected && (
        <aside className="absolute inset-y-0 right-0 z-20 w-[min(460px,52vw)] border-l border-border-subtle bg-surface-1 p-6 shadow-elev-3">
          <button className="float-right" onClick={() => setSelected(null)}>
            <X />
          </button>
          <p className="text-caption text-text-tertiary">连接器详情</p>
          <h2 className="mt-1 text-h2 font-semibold">{selected.display_name ?? selected.name}</h2>
          <p className="mt-5 text-body text-text-secondary">{selected.description}</p>
          <dl className="mt-8 grid grid-cols-2 gap-y-3 text-body-sm">
            <dt className="text-text-tertiary">状态</dt>
            <dd>{selected.status}</dd>
            <dt className="text-text-tertiary">传输</dt>
            <dd>stdio</dd>
            <dt className="text-text-tertiary">工具</dt>
            <dd>{selected.tools_count}</dd>
            <dt className="text-text-tertiary">资源</dt>
            <dd>{selected.resources_count}</dd>
          </dl>
          <p className="mt-8 text-caption text-text-tertiary">
            所有 MCP 工具调用默认需要人工确认。连接成功只代表协议握手成功。
          </p>
        </aside>
      )}
    </>
  );
}

export function ExtensionCenterPage() {
  const kind = useLocation().pathname.includes('connectors') ? 'connectors' : 'skills';
  return (
    <Layout
      sidebar={<ExtensionSidebar />}
      topBar={null}
      conversation={
        <div className="relative flex min-h-0 flex-1 flex-col">
          {kind === 'skills' ? <SkillsView /> : <ConnectorsView />}
        </div>
      }
    />
  );
}
