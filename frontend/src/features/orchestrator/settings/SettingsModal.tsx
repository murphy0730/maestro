import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { API_BASE } from '@/api/client';
import { Plus, Trash2, Check, CheckCircle2, Eye, EyeOff, Lock } from 'lucide-react';

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

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [cfg, setCfg] = useState<ProvidersConfig>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState<SectionKey | null>(null);
  const [drafts, setDrafts] = useState<Record<SectionKey, Provider>>({
    llm: { ...EMPTY_FORM },
    embedding: { ...EMPTY_FORM },
  });
  // 私密字段默认不可见；仅当用户主动点击眼睛图标时才明文显示。
  const [showKey, setShowKey] = useState<Record<SectionKey, boolean>>({
    llm: false,
    embedding: false,
  });

  useEffect(() => {
    if (!open) return;
    // 所有运行模式统一从后端 settings.json (GET /models) 读取，保证与 settings.json 联动。
    // Electron 桌面端与浏览器端共用同一份 settings.json，弹框展示与磁盘文件始终一致。
    fetch(`${API_BASE}/models`)
      .then((r) => (r.ok ? (r.json() as Promise<ProvidersConfig>) : null))
      .then((c) => setCfg(c ?? EMPTY))
      .catch(() => setCfg(EMPTY));
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
      // 统一写后端 settings.json 的 model_providers 并热更新运行中的 LLM 客户端。
      // Electron 与 Web 共用同一份 settings.json，弹框与磁盘文件始终联动、模型即时生效。
      const res = await fetch(`${API_BASE}/models`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      });
      if (!res.ok) throw new Error(`保存失败: ${res.status}`);
      // 触发后端热重载当前生效模型 (dev 经 Vite 代理; sidecar 由 Electron 重启后端)
      try {
        await fetch(`${API_BASE}/admin/reload-model`, { method: 'POST' });
      } catch {
        /* 静默: sidecar 模式后端可能整体重启 */
      }
    } catch (e) {
      console.error('保存模型配置失败', e);
    } finally {
      setSaving(false);
    }
  }

  function add(section: SectionKey) {
    const d = drafts[section];
    if (!d.name || !d.base_url || !d.model) return;
    const next: ProvidersConfig = structuredClone(cfg);
    const provider: Provider = { ...d, id: newId() };
    next[section].providers.push(provider);
    if (next[section].active_id === null) next[section].active_id = provider.id ?? null;
    setDrafts((s) => ({ ...s, [section]: { ...EMPTY_FORM } }));
    setAdding(null);
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
    <Modal
      open={open}
      onClose={onClose}
      title="模型"
      subtitle="（仅支持 OpenAI 兼容协议 API）"
      widthClassName="w-[720px]"
      bodyClassName="p-6"
    >
      <div className="space-y-8">
        {(['llm', 'embedding'] as SectionKey[]).map((sec) => (
          <section key={sec}>
            <h3 className="mb-3 text-body font-semibold text-text-primary">
              {sec === 'llm' ? 'LLM 模型' : 'Embedding 模型'}
            </h3>

            {/* 已配置模型：点击切换生效 */}
            <ul className="mb-3 space-y-2">
              {cfg[sec].providers.map((p) => {
                const active = cfg[sec].active_id === p.id;
                return (
                  <li key={p.id}>
                    <button
                      onClick={() => p.id && activate(sec, p.id)}
                      className={`group flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors duration-fast ease-out ${
                        active
                          ? 'border-accent-border bg-accent-bg'
                          : 'border-border-subtle bg-surface-1 hover:bg-surface-3'
                      }`}
                    >
                      <span
                        className={`grid h-5 w-5 flex-none place-items-center rounded-full border ${
                          active
                            ? 'border-accent text-accent-fg'
                            : 'border-border-default text-transparent'
                        }`}
                      >
                        <Check size={13} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-body-sm text-text-primary">
                          {p.name}
                        </span>
                        <span className="block truncate font-mono text-[11px] text-text-tertiary">
                          {p.model} · {p.base_url}
                        </span>
                      </span>
                      {active && (
                        <span className="flex flex-none items-center gap-1 text-caption font-medium text-accent-fg">
                          <CheckCircle2 size={13} /> 使用中
                        </span>
                      )}
                      <span
                        role="button"
                        tabIndex={-1}
                        title="删除"
                        onClick={(e) => {
                          e.stopPropagation();
                          p.id && remove(sec, p.id);
                        }}
                        className="flex-none text-text-tertiary opacity-0 transition-opacity group-hover:opacity-100 hover:text-text-secondary"
                      >
                        <Trash2 size={15} />
                      </span>
                    </button>
                  </li>
                );
              })}
              {cfg[sec].providers.length === 0 && (
                <li className="rounded-lg border border-dashed border-border-subtle px-4 py-3 text-caption text-text-tertiary">
                  尚未添加模型（降级模式）
                </li>
              )}
            </ul>

            {/* 添加模型表单：每个字段独占一行，私密字段默认掩码 */}
            {adding === sec ? (
              <div className="space-y-4 rounded-xl border border-border-subtle bg-surface-2 p-5">
                <Field label="名称">
                  <input
                    className={inputCls}
                    placeholder="如 DeepSeek"
                    value={drafts[sec].name}
                    onChange={(e) => setDrafts((s) => ({ ...s, [sec]: { ...s[sec], name: e.target.value } }))}
                  />
                </Field>
                <Field label="model">
                  <input
                    className={inputCls}
                    placeholder="如 deepseek-chat"
                    value={drafts[sec].model}
                    onChange={(e) => setDrafts((s) => ({ ...s, [sec]: { ...s[sec], model: e.target.value } }))}
                  />
                </Field>
                <Field label="base_url">
                  <input
                    className={inputCls}
                    placeholder="https://api.deepseek.com/v1"
                    value={drafts[sec].base_url}
                    onChange={(e) => setDrafts((s) => ({ ...s, [sec]: { ...s[sec], base_url: e.target.value } }))}
                  />
                </Field>
                <Field label="api_key" hint="私密信息 · 默认隐藏">
                  <div className="relative">
                    <Lock
                      size={15}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
                    />
                    <input
                      className={`${inputCls} pl-9 pr-10`}
                      placeholder="sk-..."
                      type={showKey[sec] ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={drafts[sec].api_key}
                      onChange={(e) => setDrafts((s) => ({ ...s, [sec]: { ...s[sec], api_key: e.target.value } }))}
                    />
                    <button
                      type="button"
                      title={showKey[sec] ? '隐藏' : '显示'}
                      onClick={() => setShowKey((s) => ({ ...s, [sec]: !s[sec] }))}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-tertiary transition-colors hover:bg-border-subtle hover:text-text-secondary"
                      aria-label={showKey[sec] ? '隐藏密钥' : '显示密钥'}
                    >
                      {showKey[sec] ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </Field>
                <div className="flex justify-end gap-3 pt-1">
                  <Button variant="ghost" size="sm" onClick={() => setAdding(null)}>
                    取消
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!drafts[sec].name || !drafts[sec].base_url || !drafts[sec].model}
                    onClick={() => add(sec)}
                  >
                    保存
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                fullWidth
                leadingIcon={<Plus size={14} />}
                onClick={() => setAdding(sec)}
              >
                添加模型
              </Button>
            )}
          </section>
        ))}
        {saving && <p className="text-caption text-text-tertiary">应用中，后端重启…</p>}
      </div>
    </Modal>
  );
}

const inputCls =
  'w-full rounded-lg border border-border-default bg-surface-1 px-3 py-2 text-body-sm text-text-primary outline-none transition-shadow focus:ring-2 focus:ring-accent-border placeholder:text-text-tertiary';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-body-sm font-medium text-text-secondary">{label}</span>
        {hint && (
          <span className="text-caption font-normal text-text-tertiary">{hint}</span>
        )}
      </div>
      {children}
    </div>
  );
}
