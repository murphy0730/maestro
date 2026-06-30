import type { ClarifyOption } from '@/types';

/**
 * ClarificationCard — the "Uncertain" response. When the router can't
 * confidently classify intent, the agent asks back with discrete options.
 * Styled with the uncertain (slate-violet) family. Selection is controlled
 * by props (`selectedId` + `onSelect`).
 */
interface ClarificationCardProps {
  question: string;
  detail?: string;
  options: ClarifyOption[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export function ClarificationCard({ question, detail, options, selectedId, onSelect }: ClarificationCardProps) {
  return (
    <div className="max-w-[460px] rounded-lg border border-uncertain-border bg-uncertain-bg p-[14px] font-sans shadow-elev-1">
      <div className="mb-1 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-uncertain shadow-glow-uncertain" />
        <span className="text-micro font-semibold uppercase tracking-eyebrow text-uncertain-fg">需要澄清 · Clarification</span>
      </div>
      <div className="text-body font-semibold leading-snug text-text-primary">{question}</div>
      {detail && <div className="mt-[5px] text-caption leading-normal text-text-secondary">{detail}</div>}
      <div className="mt-3 flex flex-col gap-[7px]">
        {options.map((o) => {
          const active = o.id === selectedId;
          return (
            <button
              key={o.id}
              onClick={() => onSelect?.(o.id)}
              className={`flex cursor-pointer items-center gap-[10px] rounded-md border px-[11px] py-[9px] text-left transition-colors duration-fast ease-out ${
                active ? 'border-accent-border bg-accent-bg shadow-glow-accent-sm' : 'border-border-default bg-surface-2'
              }`}
            >
              <span
                className={`grid h-4 w-4 flex-none place-items-center rounded-full border-strong ${
                  active ? 'border-accent' : 'border-border-strong'
                }`}
              >
                {active && <span className="h-[7px] w-[7px] rounded-full bg-accent shadow-glow-accent-sm" />}
              </span>
              <span className="flex-1">
                <span className="block text-body-sm font-semibold text-text-primary">{o.label}</span>
                {o.desc && <span className="mt-[1px] block text-caption text-text-tertiary">{o.desc}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
