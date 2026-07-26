export interface SubTab {
  key: string;
  label: string;
  count?: number;
}

/**
 * 子导航：2px 下划线指示，选中态同步到 `?tab=`。
 * 只有一个可见分页时不渲染——单项 tablist 没有导航意义。
 */
export function ExtensionSubTabs({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: SubTab[];
  active: string;
  onChange: (key: string) => void;
  label: string;
}) {
  if (tabs.length < 2) return null;
  return (
    <div
      role="tablist"
      aria-label={label}
      className="mb-[20px] flex gap-[4px] border-b border-border-subtle"
    >
      {tabs.map((tab) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.key)}
            className={`relative flex items-center gap-[7px] px-[14px] py-[9px] text-[12.5px] font-medium transition-colors duration-fast ${
              selected ? 'text-text-primary' : 'text-text-tertiary hover:text-text-primary'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="font-mono text-[10.5px] opacity-80">{tab.count}</span>
            )}
            {selected && (
              <span
                aria-hidden="true"
                className="absolute inset-x-[10px] -bottom-px h-[2px] rounded-[2px] bg-accent shadow-glow-accent"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
