import type { ReactNode } from 'react';
import { Check, CheckCircle2, Eye, EyeOff, Lock, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import type { Provider, SectionKey } from './modelTypes';

interface ModelProviderSectionProps {
  activeId: string | null;
  adding: boolean;
  draft: Provider;
  onActivate: (id: string) => void;
  onCancelAdding: () => void;
  onDraftChange: (patch: Partial<Provider>) => void;
  onRemove: (id: string) => void;
  onSave: () => void;
  onShowKeyChange: () => void;
  onStartAdding: () => void;
  providers: Provider[];
  section: SectionKey;
  showKey: boolean;
}

export function ModelProviderSection({
  activeId,
  adding,
  draft,
  onActivate,
  onCancelAdding,
  onDraftChange,
  onRemove,
  onSave,
  onShowKeyChange,
  onStartAdding,
  providers,
  section,
  showKey,
}: ModelProviderSectionProps) {
  const title = section === 'llm' ? 'LLM 模型' : 'Embedding 模型';

  return (
    <section>
      <h3 className="mb-3 text-body font-semibold text-text-primary">{title}</h3>
      <ul className="mb-3 space-y-2">
        {providers.map((provider) => {
          const active = activeId === provider.id;
          return (
            <li key={provider.id}>
              <button
                onClick={() => provider.id && onActivate(provider.id)}
                className={`group flex w-full items-center gap-3 rounded-md border px-4 py-3 text-left transition-colors duration-fast ease-out ${
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
                    {provider.name}
                  </span>
                  <span className="block truncate font-mono text-[11px] text-text-tertiary">
                    {provider.model} · {provider.base_url}
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
                  onClick={(event) => {
                    event.stopPropagation();
                    if (provider.id) onRemove(provider.id);
                  }}
                  className="flex-none text-text-tertiary opacity-0 transition-opacity group-hover:opacity-100 hover:text-text-secondary"
                >
                  <Trash2 size={15} />
                </span>
              </button>
            </li>
          );
        })}
        {providers.length === 0 && (
          <li className="rounded-lg border border-dashed border-border-subtle px-4 py-3 text-caption text-text-tertiary">
            尚未添加模型（降级模式）
          </li>
        )}
      </ul>
      {adding ? (
        <div className="space-y-4 rounded-md border border-border-subtle bg-surface-2 p-5">
          <Field label="名称">
            <input
              className={inputClassName}
              placeholder="如 DeepSeek"
              value={draft.name}
              onChange={(event) => onDraftChange({ name: event.target.value })}
            />
          </Field>
          <Field label="model">
            <input
              className={inputClassName}
              placeholder="如 deepseek-chat"
              value={draft.model}
              onChange={(event) => onDraftChange({ model: event.target.value })}
            />
          </Field>
          <Field label="base_url">
            <input
              className={inputClassName}
              placeholder="https://api.deepseek.com/v1"
              value={draft.base_url}
              onChange={(event) => onDraftChange({ base_url: event.target.value })}
            />
          </Field>
          <Field label="api_key" hint="私密信息 · 默认隐藏">
            <div className="relative">
              <Lock
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
              />
              <input
                className={`${inputClassName} pl-9 pr-10`}
                placeholder="sk-..."
                type={showKey ? 'text' : 'password'}
                autoComplete="new-password"
                value={draft.api_key}
                onChange={(event) => onDraftChange({ api_key: event.target.value })}
              />
              <button
                type="button"
                title={showKey ? '隐藏' : '显示'}
                onClick={onShowKeyChange}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-tertiary transition-colors hover:bg-border-subtle hover:text-text-secondary"
                aria-label={showKey ? '隐藏密钥' : '显示密钥'}
              >
                {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </Field>
          <div className="flex justify-end gap-3 pt-1">
            <Button variant="ghost" size="sm" onClick={onCancelAdding}>
              取消
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!draft.name || !draft.base_url || !draft.model}
              onClick={onSave}
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
          onClick={onStartAdding}
        >
          添加模型
        </Button>
      )}
    </section>
  );
}

const inputClassName =
  'w-full rounded-sm border border-border-default bg-surface-1 px-3 py-2 text-body-sm text-text-primary outline-none transition-shadow focus:ring-2 focus:ring-accent-border placeholder:text-text-tertiary';

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-body-sm font-medium text-text-secondary">{label}</span>
        {hint && <span className="text-caption font-normal text-text-tertiary">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
