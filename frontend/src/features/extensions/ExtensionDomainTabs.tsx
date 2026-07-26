import { Plug, Sparkles } from 'lucide-react';

export type ExtensionDomain = 'skills' | 'connectors';

const DOMAINS = [
  { key: 'skills' as const, label: '技能', icon: Sparkles },
  { key: 'connectors' as const, label: '连接器', icon: Plug },
];

/** 域级分段控件：技能 | 连接器 —— 两个同级路由的互跳。 */
export function ExtensionDomainTabs({
  domain,
  onChange,
}: {
  domain: ExtensionDomain;
  onChange: (domain: ExtensionDomain) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="扩展类型"
      className="flex flex-none gap-[2px] rounded-md border border-border-subtle bg-surface-2 p-[3px]"
    >
      {DOMAINS.map(({ key, label, icon: Icon }) => {
        const active = key === domain;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(key)}
            className={`flex items-center gap-[7px] rounded-sm px-[14px] py-[5px] text-[12.5px] font-medium transition duration-fast ease-out ${
              active
                ? 'bg-accent text-text-on-color shadow-glow-accent'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
