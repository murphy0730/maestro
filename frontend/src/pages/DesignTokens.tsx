/**
 * Design-token preview. Renders every token group extracted from the
 * Claude Design export so the palette, type, spacing, radii and glows can
 * be visually verified. No business logic — purely a confirmation surface.
 */

type Swatch = { name: string; className: string; hex?: string; note?: string };

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
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
  {
    name: '排产 Planning',
    className: 'bg-planning',
    hex: 'var(--route-planning)',
    note: 'systemBlue',
  },
  {
    name: '调度 Scheduling',
    className: 'bg-scheduling',
    hex: 'var(--route-scheduling)',
    note: 'systemOrange',
  },
  { name: '查询 Query', className: 'bg-query', hex: 'var(--route-query)', note: 'teal / mint' },
  {
    name: '不确定 Uncertain',
    className: 'bg-uncertain',
    hex: 'var(--route-uncertain)',
    note: 'systemIndigo',
  },
];

const status: Swatch[] = [
  { name: 'Success', className: 'bg-status-success', hex: 'var(--status-success)' },
  { name: 'Warning', className: 'bg-status-warning', hex: 'var(--status-warning)' },
  { name: 'Error', className: 'bg-status-error', hex: 'var(--status-error)' },
  { name: 'Info', className: 'bg-status-info', hex: 'var(--status-info)' },
];

const auth: Swatch[] = [
  { name: 'Auto · 可直接执行', className: 'bg-auth-auto', hex: 'var(--auth-auto)', note: 'green' },
  {
    name: 'Confirm · 需确认',
    className: 'bg-auth-confirm',
    hex: 'var(--auth-confirm)',
    note: 'amber',
  },
];

const accent: Swatch[] = [
  { name: 'Accent', className: 'bg-accent', hex: 'var(--accent)', note: 'brand cyan · restrained' },
  { name: 'Accent strong', className: 'bg-accent-strong', hex: 'var(--accent-strong)' },
  { name: 'Accent fg', className: 'bg-accent-fg', hex: 'var(--accent-fg)' },
];

const surfaces: Swatch[] = [
  { name: 'bg-sunken', className: 'bg-bg-sunken', hex: 'var(--bg-sunken)' },
  { name: 'bg-base', className: 'bg-bg-base', hex: 'var(--bg-base)' },
  { name: 'surface-1', className: 'bg-surface-1', hex: 'var(--surface-1)' },
  { name: 'surface-2', className: 'bg-surface-2', hex: 'var(--surface-2)' },
  { name: 'surface-3', className: 'bg-surface-3', hex: 'var(--surface-3)' },
  { name: 'surface-inset', className: 'bg-surface-inset', hex: 'var(--surface-inset)' },
];

const dataViz: Swatch[] = [
  { name: 'data-1', className: 'bg-data-1', hex: 'var(--data-1)' },
  { name: 'data-2', className: 'bg-data-2', hex: 'var(--data-2)' },
  { name: 'data-3', className: 'bg-data-3', hex: 'var(--data-3)' },
  { name: 'data-4', className: 'bg-data-4', hex: 'var(--data-4)' },
  { name: 'data-5', className: 'bg-data-5', hex: 'var(--data-5)' },
  { name: 'data-6', className: 'bg-data-6', hex: 'var(--data-6)' },
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
  ['rounded-xs', '4px'],
  ['rounded-sm', '6px'],
  ['rounded-md', '10px'],
  ['rounded-lg', '14px'],
  ['rounded-xl', '20px'],
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
          <div className="text-micro uppercase tracking-eyebrow text-accent">
            Cadence Design System
          </div>
          <h1 className="mt-2 text-display font-bold tracking-tight text-text-primary">
            Design Tokens
          </h1>
          <p className="mt-3 max-w-max-readable text-body-lg text-text-secondary">
            macOS 材质版设计 token：原始值定义在{' '}
            <span className="font-mono text-mono text-accent-fg">src/index.css</span>（浅色默认 /
            深色覆盖），由{' '}
            <span className="font-mono text-mono text-accent-fg">tailwind.config.ts</span>{' '}
            镜像为语义类。色板标签即 CSS 变量名，切换主题可对照验证两套取值。
          </p>
        </header>

        <Section
          title="路由语义色 · Route Classification"
          subtitle="colors.planning / scheduling / query / uncertain"
        >
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

        <Section
          title="字体 · Typography"
          subtitle="系统字体栈：SF Pro / PingFang SC (UI) + SF Mono (ID/参数/日志)"
        >
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-lg border border-border-subtle bg-surface-1 p-7">
              <div className="mb-4 text-micro uppercase tracking-eyebrow text-text-tertiary">
                font-sans · system / SF Pro / PingFang SC
              </div>
              <p className="text-display font-bold text-text-primary">排产 40 Display</p>
              <p className="text-h1 font-semibold text-text-primary">调度调度 H1 30</p>
              <p className="text-h3 font-medium text-text-primary">Query Engine · H3 20</p>
              <p className="mt-2 text-body text-text-secondary">
                Body 14 — 默认 UI 正文。生产排产调度 Agent 平台。The quick brown fox.
              </p>
              <p className="text-caption text-text-tertiary">Caption 12 — labels / meta</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface-inset p-7">
              <div className="mb-4 text-micro uppercase tracking-eyebrow text-text-tertiary">
                font-mono · ui-monospace / SF Mono
              </div>
              <p className="font-mono text-mono-lg text-accent-fg">ORD-2026-0042 · mono-lg 14</p>
              <p className="font-mono text-mono text-text-primary">
                qty=1200 lead_time=72h · mono 13
              </p>
              <p className="font-mono text-mono-sm text-text-secondary">
                [12:04:31] scheduler: dispatched job#88 → line-A
              </p>
              <p className="font-mono text-mono-sm text-status-success">✓ auth=auto status=ok</p>
              <p className="font-mono text-mono-sm text-auth-confirm">
                ⚠ auth=confirm needs review
              </p>
            </div>
          </div>
        </Section>

        <Section title="间距体系 · Spacing" subtitle="4px base grid · space-1 … space-13">
          <div className="space-y-2">
            {spacing.map(([k, v]) => (
              <div key={k} className="flex items-center gap-4">
                <div className="w-24 font-mono text-mono-sm text-text-tertiary">space-{k}</div>
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
