import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { usePersonalizationStore, type Personalization } from '@/stores';

const MAX_REQUIREMENTS = 2000;

const TONES: { value: Personalization['tone']; label: string }[] = [
  { value: 'default', label: '默认' },
  { value: 'professional', label: '专业' },
  { value: 'concise', label: '简洁' },
  { value: 'friendly', label: '友好' },
];

export function PersonalizationModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const data = usePersonalizationStore((s) => s.data);
  const update = usePersonalizationStore((s) => s.update);
  const [howToAddress, setHowToAddress] = useState(data.howToAddress);
  const [tone, setTone] = useState<Personalization['tone']>(data.tone);
  const [requirements, setRequirements] = useState(data.requirements);

  // 每次打开时用最新 store 值重置草稿。
  useEffect(() => {
    if (!open) return;
    setHowToAddress(data.howToAddress);
    setTone(data.tone);
    setRequirements(data.requirements);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function save() {
    update({ howToAddress: howToAddress.trim(), tone, requirements: requirements.trim() });
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="个性化设置"
      subtitle="这些偏好会用于后续会话中的称呼与回复风格。"
      widthClassName="max-w-[480px]"
      bodyClassName="p-5"
      footer={
        <>
          <span className="mr-auto text-caption text-text-tertiary">仅保存在当前设备</span>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" size="sm" onClick={save}>
            保存设置
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <Field label="如何称呼你">
          <input
            className={inputCls}
            placeholder="例如：周工、老板"
            value={howToAddress}
            onChange={(e) => setHowToAddress(e.target.value)}
          />
        </Field>

        <Field label="回复语气 / 风格">
          <div className="relative">
            <select
              className={`${inputCls} cursor-pointer appearance-none pr-9`}
              value={tone}
              onChange={(e) => setTone(e.target.value as Personalization['tone'])}
            >
              {TONES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary">
              ▾
            </span>
          </div>
        </Field>

        <Field label="你对助手的要求" hint={`${requirements.length}/${MAX_REQUIREMENTS}`}>
          <textarea
            className={`${inputCls} h-36 resize-none leading-relaxed`}
            placeholder="例如：回答时优先给出可执行结论；涉及排产请用表格呈现；避免使用过于口语化的表达。"
            maxLength={MAX_REQUIREMENTS}
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}

const inputCls =
  'w-full rounded-sm border border-border-default bg-surface-1 px-3 py-2 text-body-sm text-text-primary outline-none transition-shadow focus:ring-2 focus:ring-accent-border placeholder:text-text-tertiary';

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
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-body-sm font-medium text-text-primary">{label}</span>
        {hint && <span className="font-mono text-[11px] text-text-tertiary">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
