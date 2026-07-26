import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PackageOpen, SearchX, TriangleAlert } from 'lucide-react';
import { useDeleteSkill, useRevokeSkillTrust, useSkills, useTrustSkill } from '@/api';
import type { SkillMeta } from '@/types';
import { ExtensionSubTabs, type SubTab } from '../ExtensionSubTabs';
import { ConfirmDialog } from '../ConfirmDialog';
import { EmptyState, FilterChips } from '../shared';
import { errorMessage } from '../errors';
import { CatalogGrid } from '../catalog/CatalogGrid';
import {
  CATALOG_CATEGORIES,
  CATALOG_SKILLS,
  catalogEnabled,
} from '../catalog/staticCatalog';
import { SkillListRow } from './SkillListRow';
import { SkillDetailDrawer } from './SkillDetailDrawer';
import { SkillImportDrawer } from './SkillImportDrawer';
import { matchesSkillFilter, skillMatchesQuery, type SkillFilter } from './skillStatus';

const FILTERS: Array<{ key: SkillFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'ready', label: '可用' },
  { key: 'attention', label: '需要处理' },
  { key: 'script', label: '含脚本' },
];

/**
 * 技能域：已安装列表是真实 CRUD；「推荐 / SkillHub」只有在
 * `VITE_EXTENSION_CATALOG=on` 时才出现，且是本地静态目录，不冒充后端。
 */
export function SkillsPage() {
  const [params, setParams] = useSearchParams();
  const skillsQuery = useSkills();
  const trust = useTrustSkill();
  const revokeTrust = useRevokeSkillTrust();
  const remove = useDeleteSkill();
  const [filter, setFilter] = useState<SkillFilter>('all');
  const [pendingDelete, setPendingDelete] = useState<SkillMeta>();
  const [category, setCategory] = useState('all');

  const skills = useMemo(() => skillsQuery.data?.skills ?? [], [skillsQuery.data]);
  const discoveryErrors = skillsQuery.data?.errors ?? [];
  const query = params.get('q') ?? '';
  const browsable = catalogEnabled();
  const tab = params.get('tab') ?? (browsable ? 'recommended' : 'installed');
  const importOpen = params.get('import') === '1';
  const selected = skills.find((skill) => skill.name === params.get('skill'));

  const tabs: SubTab[] = browsable
    ? [
        { key: 'recommended', label: '推荐' },
        { key: 'hub', label: 'SkillHub 套件' },
        { key: 'installed', label: '已安装', count: skills.length },
      ]
    : [{ key: 'installed', label: '已安装', count: skills.length }];

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const visible = skills.filter(
    (skill) => skillMatchesQuery(skill, query) && matchesSkillFilter(skill, filter),
  );
  const mutationError = trust.error ?? revokeTrust.error ?? remove.error;
  const busy = trust.isPending || revokeTrust.isPending || remove.isPending;

  return (
    <>
      <ExtensionSubTabs
        tabs={tabs}
        active={tab}
        label="技能视图"
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

      {tab === 'installed' ? (
        <>
          <FilterChips options={FILTERS} value={filter} onChange={setFilter} label="技能筛选" />

          {discoveryErrors.length > 0 && (
            <div className="mb-[12px] rounded-md border border-status-warning/35 bg-status-warning-bg p-[12px] text-[11.5px] leading-[1.6] text-status-warning">
              <span className="flex items-center gap-[8px] font-medium">
                <TriangleAlert size={13} />
                {discoveryErrors.length} 个技能包无法解析，未进入列表
              </span>
              {discoveryErrors.map((item) => (
                <p key={item.path} className="m-0 mt-[4px] font-mono text-[10.5px]">
                  {item.path}：{item.reason}
                </p>
              ))}
            </div>
          )}

          <div aria-live="polite">
            {skillsQuery.isLoading && (
              <p className="py-[40px] text-center text-[12px] text-text-tertiary">正在加载技能…</p>
            )}
            {skillsQuery.error && (
              <p role="alert" className="py-[40px] text-center text-[12px] text-status-error">
                {errorMessage(skillsQuery.error)}
              </p>
            )}
          </div>

          {!skillsQuery.isLoading && !skillsQuery.error && (
            <div className="border-t border-border-subtle">
              {visible.map((skill) => (
                <SkillListRow
                  key={skill.name}
                  skill={skill}
                  busy={busy}
                  onOpen={() => setParam('skill', skill.name)}
                  onTrust={() => trust.mutate(skill.name)}
                  onDelete={() => setPendingDelete(skill)}
                />
              ))}
              {visible.length === 0 &&
                (skills.length === 0 ? (
                  <EmptyState
                    icon={<PackageOpen size={34} />}
                    title="还没有安装任何技能"
                    description="技能是 Claude Code 兼容的目录包：一段提示词，加上可选的资源与脚本。导入后由 Policy Gate 决定每次调用是否需要人工确认。"
                  />
                ) : (
                  <EmptyState
                    icon={<SearchX size={34} />}
                    title="该筛选下没有技能"
                    description="换个关键词或筛选条件试试。"
                  />
                ))}
            </div>
          )}
        </>
      ) : (
        <>
          {tab === 'hub' && (
            <FilterChips
              options={CATALOG_CATEGORIES}
              value={category}
              onChange={setCategory}
              label="技能分类"
            />
          )}
          <CatalogGrid
            emptyTitle="没有匹配的技能"
            onOpen={() => undefined}
            items={CATALOG_SKILLS.filter(
              (item) =>
                (tab === 'recommended' || category === 'all' || item.category === category) &&
                (!query ||
                  `${item.display_name}${item.description}${item.name}`
                    .toLowerCase()
                    .includes(query.toLowerCase())),
            ).map((item) => ({
              key: item.name,
              title: item.display_name,
              subtitle: `${item.publisher} · ${item.version}`,
              description: item.description,
              tags: [CATALOG_CATEGORIES.find((c) => c.key === item.category)?.label ?? item.category],
              installed: skills.some((skill) => skill.name === item.name),
            }))}
          />
          <p className="mt-[14px] text-[10.5px] leading-[1.6] text-text-tertiary">
            这是本地静态目录，用于预览目录形态。远程安装将在后端 SkillHub 接入后开放；
            现在只能通过右上角「导入技能」安装本地包。
          </p>
        </>
      )}

      {importOpen && (
        <SkillImportDrawer
          onClose={() => setParam('import', null)}
          onImported={(skill) => setParam('skill', skill.name)}
        />
      )}

      {selected && (
        <SkillDetailDrawer
          skill={selected}
          busy={busy}
          onClose={() => setParam('skill', null)}
          onTrust={() => trust.mutate(selected.name)}
          onRevokeTrust={() => revokeTrust.mutate(selected.name)}
          onDelete={() => setPendingDelete(selected)}
        />
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="卸载技能"
        confirmLabel="卸载技能"
        busy={remove.isPending}
        onCancel={() => setPendingDelete(undefined)}
        onConfirm={() => {
          const target = pendingDelete;
          if (!target) return;
          remove.mutate(target.name, {
            onSuccess: () => {
              setPendingDelete(undefined);
              if (params.get('skill') === target.name) setParam('skill', null);
            },
          });
        }}
      >
        将删除 <span className="font-mono text-text-primary">{pendingDelete?.name}</span>{' '}
        的本地包文件与注册信息。正在进行中的运行会沿用已固定的包版本直到结束。此操作不可撤销。
      </ConfirmDialog>
    </>
  );
}
