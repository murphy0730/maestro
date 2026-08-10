import { useState } from 'react';
import {
  Bell,
  CircleUserRound,
  Database,
  Info,
  Settings2,
  ShieldCheck,
  Sliders,
  X,
} from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Switch } from '@/components/ui/Switch';
import { useThemeStore } from '@/stores/themeStore';
import {
  useUiPreferencesStore,
  type RunMode,
  type TraceDefault,
} from '@/stores/uiPreferencesStore';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import { ModelSettings } from './ModelSettings';

type SectionKey = 'general' | 'models' | 'personalization';

/** 只有真实存在的设置才可保存；其余栏目明确标注暂不可用。 */
const MENU = [
  { key: 'general' as const, icon: Settings2, label: '通用', available: true },
  { key: 'models' as const, icon: Sliders, label: '模型与引擎', available: true },
  { key: 'personalization' as const, icon: CircleUserRound, label: '个性化', available: true },
  { key: null, icon: ShieldCheck, label: '授权与审批', available: false },
  { key: null, icon: Bell, label: '通知', available: false },
  { key: null, icon: Database, label: '数据与存储', available: false },
  { key: null, icon: Info, label: '关于', available: false },
];

/**
 * SettingsModal — 设计稿 I：左侧 172px 舱体菜单 + 右侧玻璃内容层，
 * 关闭键在右侧面板头。Esc / 遮罩关闭与焦点约束由 Modal 提供。
 */
export function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [section, setSection] = useState<SectionKey>('general');
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const preferences = useUiPreferencesStore();
  const personalization = usePersonalizationStore((state) => state.data);
  const updatePersonalization = usePersonalizationStore((state) => state.update);
  const activeLabel = MENU.find((item) => item.key === section)?.label ?? '通用';

  return (
    <Modal
      open={open}
      onClose={onClose}
      chrome={false}
      title="设置 · Settings"
      widthClassName="max-w-[640px]"
      bodyClassName="p-0"
    >
      <div className="grid h-[432px] grid-cols-[172px_1fr]">
        <nav
          aria-label="设置分类"
          className="flex flex-col gap-[2px] border-r border-border-subtle bg-surface-1 px-[8px] pb-[10px] pt-[14px]"
        >
          <p className="hud-label px-[10px] pb-[10px] text-text-tertiary">设置 · Settings</p>
          {MENU.map(({ key, icon: Icon, label, available }) => {
            const active = available && key === section;
            return (
              <button
                key={label}
                type="button"
                disabled={!available}
                title={available ? undefined : '当前版本暂不可用'}
                onClick={() => key && setSection(key)}
                className={`flex items-center gap-[9px] rounded-md px-[10px] py-[8px] text-left text-[12.5px] transition-colors duration-fast ease-out ${
                  active
                    ? 'bg-accent-bg text-accent'
                    : available
                      ? 'text-text-secondary hover:bg-surface-3 hover:text-text-primary'
                      : 'cursor-not-allowed text-text-tertiary opacity-55'
                }`}
              >
                <Icon size={14} />
                {label}
                {!available && <span className="ml-auto font-mono text-[9px]">暂不可用</span>}
              </button>
            );
          })}
          <p className="mt-auto px-[10px] pt-[4px] font-mono text-[9.5px] tracking-[0.12em] text-text-tertiary">
            MAESTRO v0.2.0
          </p>
        </nav>

        <div className="flex min-w-0 flex-col bg-surface-2">
          <div className="flex h-[48px] flex-none items-center gap-[10px] border-b border-border-subtle px-[16px]">
            <h2 className="m-0 text-[13.5px] font-medium text-text-primary">{activeLabel}</h2>
            <span className="flex-1" />
            <button
              type="button"
              aria-label="关闭"
              title="关闭"
              onClick={onClose}
              className="grid h-[24px] w-[24px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast hover:bg-surface-3 hover:text-accent"
            >
              <X size={14} />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-[18px] pb-[12px] pt-[2px]">
            {section === 'general' ? (
              <>
                <SettingGroup title="外观">
                  <SettingRow title="主题" description="深空为值班主场，切换即时生效">
                    <select
                      aria-label="主题"
                      value={theme}
                      onChange={(event) => setTheme(event.target.value as 'dark' | 'light')}
                      className="mode-select h-[26px] rounded-md border px-[8px] text-[11px]"
                    >
                      <option value="dark">深空（默认）</option>
                      <option value="light">极昼</option>
                    </select>
                  </SettingRow>
                  <SettingRow
                    title="减少动效"
                    description="关闭扫描线与脉冲，并遵循系统 prefers-reduced-motion"
                  >
                    <Switch
                      checked={preferences.reducedMotion}
                      onChange={preferences.setReducedMotion}
                      aria-label="减少动效"
                    />
                  </SettingRow>
                </SettingGroup>
                <SettingGroup title="对话">
                  <SettingRow
                    title="默认模式"
                    description="新会话的默认路由；后端当前仅支持自动，其他模式会明确阻止提交"
                  >
                    <select
                      aria-label="默认模式"
                      value={preferences.defaultMode}
                      onChange={(event) =>
                        preferences.setDefaultMode(event.target.value as RunMode)
                      }
                      data-mode={preferences.defaultMode}
                      className="mode-select h-[26px] rounded-md border px-[8px] text-[11px]"
                    >
                      <option value="auto">自动</option>
                      <option value="planning">排产（契约待支持）</option>
                      <option value="scheduling">调度（契约待支持）</option>
                      <option value="query">查询（契约待支持）</option>
                    </select>
                  </SettingRow>
                  <SettingRow
                    title="运行详情栏"
                    description="详情栏的默认状态，栏头与顶栏按钮可随时切换"
                  >
                    <select
                      aria-label="运行详情栏默认状态"
                      value={preferences.traceDefault}
                      onChange={(event) =>
                        preferences.setTraceDefault(event.target.value as TraceDefault)
                      }
                      className="mode-select h-[26px] rounded-md border px-[8px] text-[11px]"
                    >
                      <option value="docked">驻留</option>
                      <option value="hidden">默认隐藏</option>
                    </select>
                  </SettingRow>
                </SettingGroup>
              </>
            ) : section === 'models' ? (
              <ModelSettings />
            ) : (
              <SettingGroup title="个性化">
                <SettingRow title="称呼" description="保存在本机，用于现有个性化能力">
                  <input
                    aria-label="称呼"
                    value={personalization.howToAddress}
                    onChange={(event) =>
                      updatePersonalization({ howToAddress: event.target.value })
                    }
                    className="h-[26px] w-[144px] rounded-md border border-border-subtle bg-surface-2 px-[8px] text-[11px] outline-none focus:border-accent"
                    placeholder="例如：周工"
                  />
                </SettingRow>
                <SettingRow title="回复语气" description="选择已有 personalizationStore 支持的语气">
                  <select
                    aria-label="回复语气"
                    value={personalization.tone}
                    onChange={(event) =>
                      updatePersonalization({
                        tone: event.target.value as typeof personalization.tone,
                      })
                    }
                    className="mode-select h-[26px] rounded-md border px-[8px] text-[11px]"
                  >
                    <option value="default">默认</option>
                    <option value="professional">专业</option>
                    <option value="concise">简洁</option>
                    <option value="friendly">友好</option>
                  </select>
                </SettingRow>
              </SettingGroup>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function SettingGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="hud-label mb-[2px] mt-[14px] text-text-tertiary">{title}</h3>
      {children}
    </section>
  );
}

function SettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-[12px] border-b border-border-subtle py-[9px] last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="text-body-sm font-medium text-text-primary">{title}</div>
        <div className="mt-px text-[11.5px] leading-[1.5] text-text-tertiary">{description}</div>
      </div>
      {children}
    </div>
  );
}
