import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Plus, Trash2, CircleDot } from 'lucide-react';

type SectionKey = 'llm' | 'embedding';

interface Provider {
  id?: string;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
}

interface ProvidersConfig {
  llm: { providers: Provider[]; active_id: string | null };
  embedding: { providers: Provider[]; active_id: string | null };
}

const EMPTY: ProvidersConfig = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

const EMPTY_FORM: Provider = { name: '', base_url: '', api_key: '', model: '' };

interface ElectronProviders {
  get: () => Promise<ProvidersConfig>;
  save: (config: ProvidersConfig) => Promise<{ ok: boolean }>;
}

function getElectronProviders(): ElectronProviders | undefined {
  return (window as unknown as { electronAPI?: { providers?: ElectronProviders } }).electronAPI
    ?.providers;
}

export function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [cfg, setCfg] = useState<ProvidersConfig>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<Record<SectionKey, Provider>>({
    llm: { ...EMPTY_FORM },
    embedding: { ...EMPTY_FORM },
  });

  useEffect(() => {
    if (!open) return;
    getElectronProviders()?.get().then((c) => setCfg(c ?? EMPTY));
  }, [open]);

  // 后端重启时窗口会 reload，这里仅订阅以避免未用告警；reload 自然清理状态。
  useEffect(() => {
    if (!open) return;
    return (window as unknown as {
      electronAPI?: { onBackendReconnecting?: (cb: () => void) => () => void };
    }).electronAPI?.onBackendReconnecting?.(() => {});
  }, [open]);

  async function persist(next: ProvidersConfig) {
    setCfg(next);
    setSaving(true);
    try {
      await getElectronProviders()?.save(next);
    } finally {
      setSaving(false);
    }
  }

  function add(section: SectionKey) {
    const d = drafts[section];
    if (!d.name || !d.base_url || !d.model) return;
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].providers.push({ ...d });
    setDrafts((s) => ({ ...s, [section]: { ...EMPTY_FORM } }));
    void persist(next);
  }

  function remove(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].providers = next[section].providers.filter((p) => p.id !== id);
    if (next[section].active_id === id) next[section].active_id = null;
    void persist(next);
  }

  function activate(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].active_id = id;
    void persist(next);
  }

  return (
    <Modal open={open} onClose={onClose} title="模型供应商" widthClassName="w-[560px]">
      <div className="space-y-5">
        {(['llm', 'embedding'] as SectionKey[]).map((sec) => (
          <section key={sec}>
            <h3 className="mb-2 text-body-sm font-semibold text-text-primary">
              {sec === 'llm' ? 'LLM 供应商' : 'Embedding 供应商'}
            </h3>
            <ul className="mb-3 space-y-1">
              {cfg[sec].providers.map((p) => {
                const active = cfg[sec].active_id === p.id;
                return (
                  <li
                    key={p.id}
                    className="flex items-center gap-2 rounded-md border border-border-subtle px-2 py-1.5"
                  >
                    <button
                      title={active ? '当前生效' : '设为生效'}
                      onClick={() => p.id && activate(sec, p.id)}
                      className={`grid h-5 w-5 place-items-center rounded-full ${
                        active ? 'text-accent-fg' : 'text-text-tertiary hover:text-text-secondary'
                      }`}
                    >
                      <CircleDot size={15} />
                    </button>
                    <span className="min-w-0 flex-1 truncate text-body-sm">{p.name}</span>
                    <span className="truncate font-mono text-[10px] text-text-tertiary">{p.model}</span>
                    <button
                      title="删除"
                      onClick={() => p.id && remove(sec, p.id)}
                      className="text-text-tertiary hover:text-text-secondary"
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                );
              })}
              {cfg[sec].providers.length === 0 && (
                <li className="text-caption text-text-tertiary">尚未添加供应商（降级模式）</li>
              )}
            </ul>
            <ProviderForm
              draft={drafts[sec]}
              onChange={(d) => setDrafts((s) => ({ ...s, [sec]: d }))}
              onAdd={() => add(sec)}
            />
          </section>
        ))}
        {saving && <p className="text-caption text-text-tertiary">应用中，后端重启…</p>}
      </div>
    </Modal>
  );
}

function ProviderForm({
  draft,
  onChange,
  onAdd,
}: {
  draft: Provider;
  onChange: (d: Provider) => void;
  onAdd: () => void;
}) {
  const inputCls =
    'w-full rounded-md border border-border-default bg-surface-1 px-2 py-1 text-body-sm text-text-primary outline-none focus:ring-1 focus:ring-accent-border';
  return (
    <div className="space-y-2 rounded-md border border-border-subtle p-2">
      <div className="grid grid-cols-2 gap-2">
        <input
          className={inputCls}
          placeholder="名称"
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
        />
        <input
          className={inputCls}
          placeholder="模型 model"
          value={draft.model}
          onChange={(e) => onChange({ ...draft, model: e.target.value })}
        />
      </div>
      <input
        className={inputCls}
        placeholder="base_url"
        value={draft.base_url}
        onChange={(e) => onChange({ ...draft, base_url: e.target.value })}
      />
      <input
        className={inputCls}
        placeholder="api_key"
        type="password"
        value={draft.api_key}
        onChange={(e) => onChange({ ...draft, api_key: e.target.value })}
      />
      <button
        onClick={onAdd}
        className="inline-flex items-center gap-1 rounded-md border border-border-default bg-surface-1 px-2 py-1 text-body-sm font-semibold text-text-primary hover:bg-surface-3"
      >
        <Plus size={14} /> 添加供应商
      </button>
    </div>
  );
}
