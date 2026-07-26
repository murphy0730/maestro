import type { ReactNode } from 'react';

const TONES = [
  'text-accent border-accent-border bg-accent-bg',
  'text-mode-planning border-mode-planning/35 bg-mode-planning-bg',
  'text-mode-scheduling border-mode-scheduling/35 bg-mode-scheduling-bg',
  'text-mode-query border-mode-query/35 bg-mode-query-bg',
  'text-path-controlled border-path-controlled/35 bg-path-controlled-bg',
];

/** 名称派生的方形字母图标——没有真实图标资源时不伪造品牌。 */
export function ExtensionIcon({ name, size = 32 }: { name: string; size?: number }) {
  const code = Array.from(name).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const tone = TONES[code % TONES.length];
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
      className={`grid flex-none place-items-center rounded-md border font-semibold uppercase ${tone}`}
    >
      {name.slice(0, 2)}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-[10px] px-[20px] py-[70px] text-center">
      <span className="text-text-tertiary">{icon}</span>
      <h3 className="m-0 text-[16px] font-semibold text-text-primary">{title}</h3>
      <p className="m-0 max-w-[420px] text-[12.5px] leading-[1.7] text-text-secondary">
        {description}
      </p>
      {action}
    </div>
  );
}

/** 列表页的筛选 chip 行。 */
export function FilterChips<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ key: T; label: string }>;
  value: T;
  onChange: (key: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="mb-[16px] flex flex-wrap gap-[6px]">
      {options.map((option) => {
        const active = option.key === value;
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.key)}
            className={`rounded-pill border px-[12px] py-[5px] text-[11.5px] transition-colors duration-fast ${
              active
                ? 'border-accent-border bg-accent-bg text-accent'
                : 'border-border-subtle bg-surface-2 text-text-secondary hover:border-border-strong hover:text-text-primary'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export const rowButton =
  'rounded-sm border border-transparent px-[10px] py-[4px] text-[11px] text-text-tertiary transition-colors duration-fast hover:border-border-strong hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40';
export const dangerRowButton =
  'rounded-sm border border-transparent px-[10px] py-[4px] text-[11px] text-text-tertiary transition-colors duration-fast hover:border-status-error/45 hover:bg-status-error-bg hover:text-status-error disabled:cursor-not-allowed disabled:opacity-40';
export const primaryButton =
  'inline-flex items-center gap-[7px] rounded-sm bg-accent px-[14px] py-[7px] text-[12px] font-medium text-text-on-color shadow-glow-accent transition duration-fast ease-out hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40';
export const ghostButton =
  'inline-flex items-center gap-[7px] rounded-sm border border-border-strong px-[14px] py-[7px] text-[12px] text-text-secondary transition-colors duration-fast hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40';
export const dangerButton =
  'inline-flex items-center gap-[7px] rounded-sm border border-status-error/45 px-[14px] py-[7px] text-[12px] text-status-error transition-colors duration-fast hover:bg-status-error-bg disabled:cursor-not-allowed disabled:opacity-40';
export const fieldInput =
  'w-full rounded-md border border-border-subtle bg-surface-2 px-[12px] py-[8px] text-[12.5px] text-text-primary outline-none transition-colors duration-fast focus:border-accent placeholder:text-text-tertiary';
