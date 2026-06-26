/**
 * Design-token preview. Renders every token group extracted from the
 * Claude Design export so the palette, type, spacing, radii and glows can
 * be visually verified. No business logic — purely a confirmation surface.
 */

type Swatch = { name: string; className: string; hex?: string; note?: string };

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <div className="mb-6 border-b border-border-subtle pb-3">
        <h2 className="text-h3 font-semibold text-text-primary">{title}</h2>
        {subtitle && <p className="mt-1 font-mono text-mono-sm text-text-tertiary">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function SwatchCard({ name, className, hex, note }: Swatch) {
  return (
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-1">
      <div className={`h-20 w-full ${className}`} />
      <div className="px-4 py-3">
        <div className="text-body-sm font-medium text-text-primary">{name}</div>
        {hex && <div className="font-mono text-mono-sm text-text-tertiary">{hex}</div>}
        {note && <div className="mt-1 text-caption text-text-secondary">{note}</div>}
      </div>
    </div>
  );
}

function Grid({ items }: { items: Swatch[] }) {
  return (
    <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((s) => (
        <SwatchCard key={s.name} {...s} />
      ))}
    </div>
  );
}

const routes: Swatch[] = [
  { name: '排产 Planning', className: 'bg-planning', hex: '#4C9DF7', note: '冷蓝 · cool azure' },
  { name: '调度 Scheduling', className: 'bg-scheduling', hex: '#F7A53B', note: '橙 · amber' },
  { name: '查询 Query', className: 'bg-query', hex: '#16C79A', note: 'teal · 青绿' },
  { name: '不确定 Uncertain', className: 'bg-uncertain', hex: '#8B86B8', note: '灰紫 · slate-violet' },
];

const status: Swatch[] = [
  { name: 'Success', className: 'bg-status-success', hex: '#34D399' },
  { name: 'Warning', className: 'bg-status-warning', hex: '#FBBF24' },
  { name: 'Error', className: 'bg-status-error', hex: '#F8736A' },
  { name: 'Info', className: 'bg-status-info', hex: '#5DA6FF' },
];

const auth: Swatch[] = [
  { name: 'Auto · 可直接执行', className: 'bg-auth-auto', hex: '#2CC56F', note: 'green' },
  { name: 'Confirm · 需确认', className: 'bg-auth-confirm', hex: '#F59E0B', note: 'amber' },
];

const accent: Swatch[] = [
  { name: 'Accent', className: 'bg-accent', hex: '#2DE2E6', note: 'electric cyan' },
  { name: 'Accent strong', className: 'bg-accent-strong', hex: '#18C8D6' },
  { name: 'Accent fg', className: 'bg-accent-fg', hex: '#7CF1F2' },
];

const surfaces: Swatch[] = [
  { name: 'bg-sunken', className: 'bg-bg-sunken', hex: '#060910' },
  { name: 'bg-base', className: 'bg-bg-base', hex: '#0A0E16' },
  { name: 'surface-1', className: 'bg-surface-1', hex: '#10151F' },
  { name: 'surface-2', className: 'bg-surface-2', hex: '#161D2A' },
  { name: 'surface-3', className: 'bg-surface-3', hex: '#1E2736' },
  { name: 'surface-inset', className: 'bg-surface-inset', hex: '#0C1018' },
];

const dataViz: Swatch[] = [
  { name: 'data-1', className: 'bg-data-1', hex: '#4C9DF7' },
  { name: 'data-2', className: 'bg-data-2', hex: '#16C79A' },
  { name: 'data-3', className: 'bg-data-3', hex: '#F7A53B' },
  { name: 'data-4', className: 'bg-data-4', hex: '#8B86B8' },
  { name: 'data-5', className: 'bg-data-5', hex: '#2DE2E6' },
  { name: 'data-6', className: 'bg-data-6', hex: '#F8736A' },
];

const spacing = [
  ['1', '2px'],
  ['2', '4px'],
  ['3', '6px'],
  ['4', '8px'],
  ['5', '12px'],
  ['6', '16px'],
  ['7', '20px'],
  ['8', '24px'],
  ['9', '32px'],
  ['10', '40px'],
  ['11', '48px'],
  ['12', '64px'],
  ['13', '80px'],
];

const radii = [
  ['rounded-xs', '3px'],
  ['rounded-sm', '5px'],
  ['rounded-md', '8px'],
  ['rounded-lg', '12px'],
  ['rounded-xl', '16px'],
  ['rounded-pill', '999px'],
];

const glows = [
  { name: 'glow-accent', className: 'shadow-glow-accent' },
  { name: 'glow-planning', className: 'shadow-glow-planning' },
  { name: 'glow-scheduling', className: 'shadow-glow-scheduling' },
  { name: 'glow-query', className: 'shadow-glow-query' },
  { name: 'glow-uncertain', className: 'shadow-glow-uncertain' },
  { name: 'glow-success', className: 'shadow-glow-success' },
  { name: 'glow-confirm', className: 'shadow-glow-confirm' },
];

export function DesignTokens() {
  return (
    <div className="min-h-full bg-bg-base px-9 py-11">
      <div className="mx-auto max-w-[1100px]">
        <header className="mb-12">
          <div className="text-micro uppercase tracking-eyebrow text-accent">Cadence Design System</div>
          <h1 className="mt-2 text-display font-bold tracking-tight text-text-primary">Design Tokens</h1>
          <p className="mt-3 max-w-max-readable text-body-lg text-text-secondary">
            从 <span className="font-mono text-mono text-accent-fg">design-export/Maestro.html</span>{' '}
            提取并落地到 <span className="font-mono text-mono text-accent-fg">tailwind.config.ts</span>。
            用于确认配色与字体是否正确。
          </p>
        </header>

        <Section title="路由语义色 · Route Classification" subtitle="colors.planning / scheduling / query / uncertain">
          <Grid items={routes} />
          <div className="mt-5 flex flex-wrap gap-4">
            {routes.map((r) => (
              <span
                key={r.name}
                className={`rounded-pill border px-5 py-2 text-body-sm font-medium ${r.className.replace('bg-', 'text-')} ${r.className.replace('bg-', 'border-')}/40`}
                style={{ backgroundColor: 'var(--surface-1)' }}
              >
                {r.name}
              </span>
            ))}
          </div>
        </Section>

        <Section title="状态色 · Status" subtitle="colors.status.*">
          <Grid items={status} />
        </Section>

        <Section title="授权级别 · Action Authorization" subtitle="colors.auth.*">
          <Grid items={auth} />
        </Section>

        <Section title="强调色 · Accent" subtitle="colors.accent.*">
          <Grid items={accent} />
        </Section>

        <Section title="背景层级 · Surfaces" subtitle="depth: sunken < base < surfaces">
          <Grid items={surfaces} />
        </Section>

        <Section title="数据可视化序列 · Data-viz" subtitle="colors.data-1 … data-6">
          <Grid items={dataViz} />
        </Section>

        <Section title="字体 · Typography" subtitle="IBM Plex Sans (UI) + IBM Plex Mono (ID/参数/日志)">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-lg border border-border-subtle bg-surface-1 p-7">
              <div className="mb-4 text-micro uppercase tracking-eyebrow text-text-tertiary">font-sans · IBM Plex Sans</div>
              <p className="text-display font-bold text-text-primary">排产 40 Display</p>
              <p className="text-h1 font-semibold text-text-primary">调度调度 H1 30</p>
              <p className="text-h3 font-medium text-text-primary">Query Engine · H3 20</p>
              <p className="mt-2 text-body text-text-secondary">
                Body 14 — 默认 UI 正文。生产排产调度 Agent 平台。The quick brown fox.
              </p>
              <p className="text-caption text-text-tertiary">Caption 12 — labels / meta</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface-inset p-7">
              <div className="mb-4 text-micro uppercase tracking-eyebrow text-text-tertiary">font-mono · IBM Plex Mono</div>
              <p className="font-mono text-mono-lg text-accent-fg">ORD-2026-0042 · mono-lg 14</p>
              <p className="font-mono text-mono text-text-primary">qty=1200 lead_time=72h · mono 13</p>
              <p className="font-mono text-mono-sm text-text-secondary">
                [12:04:31] scheduler: dispatched job#88 → line-A
              </p>
              <p className="font-mono text-mono-sm text-status-success">✓ auth=auto status=ok</p>
              <p className="font-mono text-mono-sm text-auth-confirm">⚠ auth=confirm needs review</p>
            </div>
          </div>
        </Section>

        <Section title="间距体系 · Spacing" subtitle="4px base grid · space-1 … space-13">
          <div className="space-y-2">
            {spacing.map(([k, v]) => (
              <div key={k} className="flex items-center gap-4">
                <div className="w-24 font-mono text-mono-sm text-text-tertiary">
                  space-{k}
                </div>
                <div className="h-4 rounded-xs bg-accent" style={{ width: v }} />
                <div className="font-mono text-mono-sm text-text-secondary">{v}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="圆角 · Radii" subtitle="rounded-xs … rounded-pill">
          <div className="flex flex-wrap gap-6">
            {radii.map(([cls, v]) => (
              <div key={cls} className="text-center">
                <div className={`h-20 w-20 border border-accent-border bg-surface-2 ${cls}`} />
                <div className="mt-2 font-mono text-mono-sm text-text-tertiary">{v}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="发光描边 · Glow" subtitle="shadow-glow-*">
          <div className="flex flex-wrap gap-7">
            {glows.map((g) => (
              <div
                key={g.name}
                className={`flex h-20 w-44 items-center justify-center rounded-lg border border-border-default bg-surface-1 ${g.className}`}
              >
                <span className="font-mono text-mono-sm text-text-secondary">{g.name}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
