import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { API_BASE } from '@/api/client';
import { ModelProviderSection } from './ModelProviderSection';
import {
  EMPTY_CONFIG,
  EMPTY_PROVIDER,
  type Provider,
  type ProvidersConfig,
  type SectionKey,
} from './modelTypes';

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [config, setConfig] = useState<ProvidersConfig>(EMPTY_CONFIG);
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState<SectionKey | null>(null);
  const [drafts, setDrafts] = useState<Record<SectionKey, Provider>>({
    llm: { ...EMPTY_PROVIDER },
    embedding: { ...EMPTY_PROVIDER },
  });
  const [showKey, setShowKey] = useState<Record<SectionKey, boolean>>({
    llm: false,
    embedding: false,
  });

  useEffect(() => {
    if (!open) return;
    fetch(`${API_BASE}/models`)
      .then((response) => (response.ok ? (response.json() as Promise<ProvidersConfig>) : null))
      .then((next) => setConfig(next ?? EMPTY_CONFIG))
      .catch(() => setConfig(EMPTY_CONFIG));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    return (
      window as unknown as {
        electronAPI?: { onBackendReconnecting?: (callback: () => void) => () => void };
      }
    ).electronAPI?.onBackendReconnecting?.(() => {});
  }, [open]);

  async function persist(next: ProvidersConfig) {
    setConfig(next);
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/models`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      });
      if (!response.ok) throw new Error(`保存失败: ${response.status}`);
      await fetch(`${API_BASE}/admin/reload-model`, { method: 'POST' }).catch(() => undefined);
    } catch (error) {
      console.error('保存模型配置失败', error);
    } finally {
      setSaving(false);
    }
  }

  function add(section: SectionKey) {
    const draft = drafts[section];
    if (!draft.name || !draft.base_url || !draft.model) return;
    const next: ProvidersConfig = structuredClone(config);
    const provider: Provider = { ...draft, id: newId() };
    next[section].providers.push(provider);
    if (next[section].active_id === null) next[section].active_id = provider.id ?? null;
    setDrafts((current) => ({ ...current, [section]: { ...EMPTY_PROVIDER } }));
    setAdding(null);
    void persist(next);
  }

  function remove(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(config);
    next[section].providers = next[section].providers.filter((provider) => provider.id !== id);
    if (next[section].active_id === id) next[section].active_id = null;
    void persist(next);
  }

  function activate(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(config);
    next[section].active_id = id;
    void persist(next);
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="模型设置"
      subtitle="配置推理与检索模型。当前仅支持 OpenAI 兼容协议 API。"
      widthClassName="max-w-[520px]"
      bodyClassName="p-5"
      footer={
        <>
          <span className="mr-auto text-caption text-text-tertiary">
            {saving ? '正在应用配置，后端重启中…' : '模型变更保存后即时生效'}
          </span>
          <Button variant="primary" size="sm" onClick={onClose}>
            完成
          </Button>
        </>
      }
    >
      <div className="space-y-7">
        {(['llm', 'embedding'] as SectionKey[]).map((section) => (
          <ModelProviderSection
            key={section}
            section={section}
            providers={config[section].providers}
            activeId={config[section].active_id}
            adding={adding === section}
            draft={drafts[section]}
            showKey={showKey[section]}
            onActivate={(id) => activate(section, id)}
            onRemove={(id) => remove(section, id)}
            onStartAdding={() => setAdding(section)}
            onCancelAdding={() => setAdding(null)}
            onDraftChange={(patch) =>
              setDrafts((current) => ({
                ...current,
                [section]: { ...current[section], ...patch },
              }))
            }
            onShowKeyChange={() =>
              setShowKey((current) => ({ ...current, [section]: !current[section] }))
            }
            onSave={() => add(section)}
          />
        ))}
      </div>
    </Modal>
  );
}
