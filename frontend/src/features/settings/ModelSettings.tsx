import { useState } from 'react';
import { Check, Eye, EyeOff, Loader2, Pencil, Plug, Plus, Trash2 } from 'lucide-react';
import { useModels, useSaveModels, useTestModelProvider } from '@/api';
import { errorMessage } from '@/features/extensions/errors';
import { Badge } from '@/components/ui/Badge';
import type { ModelProvider, ModelSectionKey, ModelTestResult, ModelsConfig } from '@/types';

const EMPTY_CONFIG: ModelsConfig = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

const EMPTY_DRAFT: ModelProvider = { name: '', base_url: '', model: '', api_key: '' };

const SECTIONS: { key: ModelSectionKey; title: string; hint: string }[] = [
  {
    key: 'llm',
    title: '推理模型',
    hint: '仅支持 OpenAI 兼容协议。启用项优先于 .env，保存后无需重启即生效。',
  },
  {
    key: 'embedding',
    title: '嵌入模型',
    hint: '当前 Runtime 尚未使用嵌入能力，配置会保存但暂不生效。',
  },
];

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * ModelSettings — 设置弹框的「模型与引擎」面板。
 *
 * 配置存在后端 `<数据根>/settings.json`，不是本机 localStorage：切换启用项要让
 * 运行中的后端立刻换连接，这只有后端热更新能做到。密钥永不回传，编辑既有条目时
 * 留空即保留原值（由后端 merge_preserving_secrets 负责）。
 */
export function ModelSettings() {
  const { data, isLoading } = useModels();
  const save = useSaveModels();
  const config = data ?? EMPTY_CONFIG;

  const [editing, setEditing] = useState<{ section: ModelSectionKey; id: string | null } | null>(
    null,
  );
  const [draft, setDraft] = useState<ModelProvider>(EMPTY_DRAFT);
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState('');

  async function persist(next: ModelsConfig) {
    setError('');
    try {
      await save.mutateAsync(next);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  function startAdding(section: ModelSectionKey) {
    setEditing({ section, id: null });
    setDraft(EMPTY_DRAFT);
    setShowKey(false);
    setError('');
  }

  function startEditing(section: ModelSectionKey, provider: ModelProvider) {
    setEditing({ section, id: provider.id ?? null });
    setDraft({ ...provider, api_key: '' });
    setShowKey(false);
    setError('');
  }

  function commitDraft() {
    if (!editing) return;
    const { section, id } = editing;
    const next = structuredClone(config);
    if (id) {
      next[section].providers = next[section].providers.map((item) =>
        item.id === id ? { ...draft, id } : item,
      );
    } else {
      const created = { ...draft, id: newId() };
      next[section].providers = [...next[section].providers, created];
      // 第一个添加的条目直接启用，省掉一次多余的点击。
      if (next[section].active_id === null) next[section].active_id = created.id;
    }
    setEditing(null);
    void persist(next);
  }

  function activate(section: ModelSectionKey, id: string) {
    if (config[section].active_id === id) return;
    const next = structuredClone(config);
    next[section].active_id = id;
    void persist(next);
  }

  function remove(section: ModelSectionKey, id: string) {
    const next = structuredClone(config);
    next[section].providers = next[section].providers.filter((item) => item.id !== id);
    // 删掉启用项就回退到 .env，而不是悄悄启用另一个。
    if (next[section].active_id === id) next[section].active_id = null;
    void persist(next);
  }

  if (isLoading) {
    return <p className="py-[18px] text-[11.5px] text-text-tertiary">正在读取模型配置…</p>;
  }

  return (
    <div>
      {SECTIONS.map(({ key, title, hint }) => (
        <section key={key}>
          <h3 className="hud-label mb-[2px] mt-[14px] text-text-tertiary">{title}</h3>
          <p className="mb-[8px] text-[11.5px] leading-[1.5] text-text-tertiary">{hint}</p>

          <div role="radiogroup" aria-label={title} className="flex flex-col gap-[2px]">
            {config[key].providers.map((provider) => (
              <ProviderRow
                key={provider.id}
                provider={provider}
                active={config[key].active_id === provider.id}
                section={key}
                onActivate={() => provider.id && activate(key, provider.id)}
                onEdit={() => startEditing(key, provider)}
                onRemove={() => provider.id && remove(key, provider.id)}
              />
            ))}
          </div>

          {config[key].providers.length === 0 && (
            <p className="rounded-[12px] border border-dashed border-border-subtle px-[14px] py-[12px] text-[11.5px] text-text-tertiary">
              {key === 'llm' ? '尚未添加模型 · 当前为降级模式' : '尚未添加嵌入模型'}
            </p>
          )}

          {editing?.section === key ? (
            <ProviderForm
              draft={draft}
              section={key}
              editingId={editing.id}
              showKey={showKey}
              onToggleKey={() => setShowKey((value) => !value)}
              onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
              onCancel={() => setEditing(null)}
              onSubmit={commitDraft}
            />
          ) : (
            <button
              type="button"
              onClick={() => startAdding(key)}
              className="mt-[8px] flex w-full items-center justify-center gap-[8px] rounded-[8px] border border-border-strong px-[14px] py-[7px] text-[12px] font-medium text-text-primary transition-colors duration-fast ease-out hover:border-accent hover:text-accent"
            >
              <Plus size={14} />
              添加模型
            </button>
          )}
        </section>
      ))}

      {error && (
        <p role="alert" className="mt-[12px] text-[11.5px] leading-[1.5] text-status-error">
          {error}
        </p>
      )}
      {!error && save.isSuccess && (
        <p className="mt-[12px] text-[11.5px] text-text-tertiary">
          {save.data?.available ? '已保存并生效' : '已保存 · 未配置可用密钥，仍为降级模式'}
        </p>
      )}
    </div>
  );
}

function ProviderRow({
  provider,
  active,
  section,
  onActivate,
  onEdit,
  onRemove,
}: {
  provider: ModelProvider;
  active: boolean;
  section: ModelSectionKey;
  onActivate: () => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const test = useTestModelProvider();
  const [result, setResult] = useState<ModelTestResult | null>(null);

  async function runTest() {
    setResult(null);
    try {
      setResult(
        await test.mutateAsync({
          section,
          id: provider.id,
          base_url: provider.base_url,
          model: provider.model,
          api_key: '',
        }),
      );
    } catch (cause) {
      setResult({ ok: false, error: errorMessage(cause), latency_ms: 0 });
    }
  }

  return (
    <div className="group relative">
      <button
        type="button"
        role="radio"
        aria-checked={active}
        onClick={onActivate}
        className={`flex w-full items-center gap-[10px] rounded-[9px] px-[10px] py-[8px] text-left transition-colors duration-fast ease-out ${
          active ? 'bg-accent-bg' : 'hover:bg-surface-3'
        }`}
      >
        <span
          aria-hidden
          className={`grid h-[16px] w-[16px] flex-none place-items-center rounded-full border ${
            active
              ? 'border-accent bg-accent text-text-on-color shadow-[var(--glow-accent)]'
              : 'border-border-strong text-transparent'
          }`}
        >
          <Check size={10} strokeWidth={3} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-[8px]">
            <span
              className={`truncate text-[13px] font-medium ${active ? 'text-accent' : 'text-text-primary'}`}
            >
              {provider.name || '未命名'}
            </span>
            {provider.api_key_set === false && <Badge tone="warning">未配置密钥</Badge>}
          </span>
          <span className="mt-px block truncate font-mono text-[11px] text-text-tertiary">
            {provider.model} · {provider.base_url || '默认地址'}
          </span>
        </span>
        {active && (
          <span className="flex-none font-mono text-[9.5px] uppercase tracking-[0.12em] text-accent">
            使用中
          </span>
        )}
      </button>

      <div className="absolute right-[6px] top-1/2 hidden -translate-y-1/2 items-center gap-[2px] rounded-[7px] border border-border-strong bg-surface-3 p-[2px] group-hover:flex group-focus-within:flex">
        <RowAction label="测试连接" onClick={runTest} disabled={test.isPending}>
          {test.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plug size={12} />}
        </RowAction>
        <RowAction label="编辑" onClick={onEdit}>
          <Pencil size={12} />
        </RowAction>
        <RowAction label="删除" onClick={onRemove} danger>
          <Trash2 size={12} />
        </RowAction>
      </div>

      {result && (
        <p
          role="status"
          className={`px-[10px] pb-[6px] text-[11px] ${result.ok ? 'text-status-success' : 'text-status-error'}`}
        >
          {result.ok ? `连接正常 · ${result.latency_ms}ms` : `连接失败：${result.error}`}
        </p>
      )}
    </div>
  );
}

function RowAction({
  label,
  onClick,
  children,
  danger = false,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`grid h-[20px] w-[20px] place-items-center rounded-[5px] text-text-tertiary transition-colors duration-fast disabled:opacity-40 ${
        danger
          ? 'hover:bg-surface-1 hover:text-status-error'
          : 'hover:bg-surface-1 hover:text-accent'
      }`}
    >
      {children}
    </button>
  );
}

function ProviderForm({
  draft,
  section,
  editingId,
  showKey,
  onToggleKey,
  onChange,
  onCancel,
  onSubmit,
}: {
  draft: ModelProvider;
  section: ModelSectionKey;
  editingId: string | null;
  showKey: boolean;
  onToggleKey: () => void;
  onChange: (patch: Partial<ModelProvider>) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const test = useTestModelProvider();
  const [result, setResult] = useState<ModelTestResult | null>(null);
  const complete = Boolean(draft.name && draft.model);

  async function runTest() {
    setResult(null);
    try {
      setResult(
        await test.mutateAsync({
          section,
          id: editingId ?? undefined,
          base_url: draft.base_url,
          model: draft.model,
          api_key: draft.api_key,
        }),
      );
    } catch (cause) {
      setResult({ ok: false, error: errorMessage(cause), latency_ms: 0 });
    }
  }

  return (
    <div className="mt-[8px] rounded-[12px] border border-border-subtle bg-surface-1 p-[14px]">
      <Field label="名称">
        <input
          aria-label="名称"
          value={draft.name}
          placeholder="如 DeepSeek"
          onChange={(event) => onChange({ name: event.target.value })}
          className={INPUT}
        />
      </Field>
      <Field label="model">
        <input
          aria-label="model"
          value={draft.model}
          placeholder={section === 'llm' ? 'deepseek-chat' : 'text-embedding-3-small'}
          onChange={(event) => onChange({ model: event.target.value })}
          className={INPUT}
        />
      </Field>
      <Field label="base_url">
        <input
          aria-label="base_url"
          value={draft.base_url}
          placeholder="https://api.deepseek.com"
          onChange={(event) => onChange({ base_url: event.target.value })}
          className={INPUT}
        />
      </Field>
      <Field label="api_key">
        <div className="relative">
          <input
            aria-label="api_key"
            type={showKey ? 'text' : 'password'}
            autoComplete="new-password"
            value={draft.api_key}
            placeholder={editingId ? '已保存 · 留空则不变' : 'sk-...'}
            onChange={(event) => onChange({ api_key: event.target.value })}
            className={`${INPUT} pr-[34px]`}
          />
          <button
            type="button"
            aria-label={showKey ? '隐藏密钥' : '显示密钥'}
            title={showKey ? '隐藏密钥' : '显示密钥'}
            onClick={onToggleKey}
            className="absolute right-[8px] top-1/2 -translate-y-1/2 text-text-tertiary transition-colors hover:text-text-secondary"
          >
            {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </Field>

      {result && (
        <p
          role="status"
          className={`mt-[8px] text-[11px] ${result.ok ? 'text-status-success' : 'text-status-error'}`}
        >
          {result.ok ? `连接正常 · ${result.latency_ms}ms` : `连接失败：${result.error}`}
        </p>
      )}

      <div className="mt-[12px] flex items-center gap-[8px]">
        <button
          type="button"
          onClick={runTest}
          disabled={!draft.model || test.isPending}
          className="flex items-center gap-[6px] rounded-[6px] border border-border-strong px-[12px] py-[5px] text-[11.5px] text-text-primary transition-colors duration-fast hover:border-accent hover:text-accent disabled:opacity-40"
        >
          {test.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plug size={12} />}
          测试连接
        </button>
        <span className="flex-1" />
        <button
          type="button"
          onClick={onCancel}
          className="rounded-[6px] border border-border-strong px-[12px] py-[5px] text-[11.5px] text-text-primary transition-colors duration-fast hover:border-accent hover:text-accent"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!complete}
          className="rounded-[6px] bg-accent px-[12px] py-[5px] text-[11.5px] font-medium text-text-on-color shadow-[var(--glow-accent)] transition-[filter] duration-fast hover:brightness-110 disabled:opacity-40"
        >
          保存
        </button>
      </div>
    </div>
  );
}

const INPUT =
  'w-full rounded-[8px] border border-border-subtle bg-surface-2 px-[12px] py-[7px] text-[12.5px] text-text-primary outline-none transition-colors duration-fast placeholder:text-text-tertiary focus:border-accent';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-[10px] last:mb-0">
      <div className="mb-[4px] font-mono text-[10.5px] uppercase tracking-[0.12em] text-text-tertiary">
        {label}
      </div>
      {children}
    </div>
  );
}
