import type { Config } from 'tailwindcss';

/**
 * Cadence design tokens — extracted verbatim from the Claude Design export
 * (design-export/Maestro.html). The CSS custom properties live in src/index.css;
 * this file mirrors them as semantic Tailwind utilities so JSX can use
 * `bg-planning`, `text-route-query-fg`, `shadow-glow-scheduling`, etc.
 *
 * Source of truth for the raw values is index.css :root. Where a token is a
 * single solid color we inline the hex here; alpha-blended fills/borders/glows
 * reference the CSS vars so there is exactly one definition.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ---- Base backgrounds (depth: sunken < base < surfaces) ----
        'bg-sunken': 'var(--bg-sunken)',
        'bg-base': 'var(--bg-base)',
        'surface-1': 'var(--surface-1)',
        'surface-2': 'var(--surface-2)',
        'surface-3': 'var(--surface-3)',
        'surface-inset': 'var(--surface-inset)',

        // ---- Text ----
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-tertiary': 'var(--text-tertiary)',
        'text-disabled': 'var(--text-disabled)',
        'text-on-color': 'var(--text-on-color)',
        'text-inverse': 'var(--text-inverse)',

        // ---- Borders / hairlines (alpha → via CSS var) ----
        'border-subtle': 'var(--border-subtle)',
        'border-default': 'var(--border-default)',
        'border-strong': 'var(--border-strong)',
        'border-accent': 'var(--border-accent)',

        // ============================================================
        // ROUTE CLASSIFICATION — four engine families
        // ============================================================
        // 排产 Planning — cool azure/blue
        planning: {
          DEFAULT: '#4C9DF7',
          fg: 'var(--route-planning-fg)',
          bg: 'var(--route-planning-bg)',
          border: 'var(--route-planning-border)',
        },
        // 调度 Scheduling — amber/orange
        scheduling: {
          DEFAULT: '#F7A53B',
          fg: 'var(--route-scheduling-fg)',
          bg: 'var(--route-scheduling-bg)',
          border: 'var(--route-scheduling-border)',
        },
        // 查询 Query — teal / 青绿
        query: {
          DEFAULT: '#16C79A',
          fg: 'var(--route-query-fg)',
          bg: 'var(--route-query-bg)',
          border: 'var(--route-query-border)',
        },
        // 不确定 Uncertain — muted slate-violet
        uncertain: {
          DEFAULT: '#8B86B8',
          fg: 'var(--route-uncertain-fg)',
          bg: 'var(--route-uncertain-bg)',
          border: 'var(--route-uncertain-border)',
        },

        // ============================================================
        // STATUS — feedback states
        // ============================================================
        status: {
          success: '#34D399',
          'success-bg': 'var(--status-success-bg)',
          warning: '#FBBF24',
          'warning-bg': 'var(--status-warning-bg)',
          error: '#F8736A',
          'error-bg': 'var(--status-error-bg)',
          info: '#5DA6FF',
          'info-bg': 'var(--status-info-bg)',
        },

        // ============================================================
        // ACTION AUTHORIZATION — auto (green) vs confirm (amber)
        // ============================================================
        auth: {
          auto: '#2CC56F',
          'auto-bg': 'var(--auth-auto-bg)',
          'auto-border': 'var(--auth-auto-border)',
          confirm: '#F59E0B',
          'confirm-bg': 'var(--auth-confirm-bg)',
          'confirm-border': 'var(--auth-confirm-border)',
        },

        // ============================================================
        // ACCENT — electric cyan (small-area glow / focus / highlights)
        // ============================================================
        accent: {
          DEFAULT: '#2DE2E6',
          strong: '#18C8D6',
          fg: 'var(--accent-fg)',
          bg: 'var(--accent-bg)',
          border: 'var(--accent-border)',
        },

        // ---- Data-viz sequence (charts, gantt tracks) ----
        'data-1': '#4C9DF7',
        'data-2': '#16C79A',
        'data-3': '#F7A53B',
        'data-4': '#8B86B8',
        'data-5': '#2DE2E6',
        'data-6': '#F8736A',
      },

      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SFMono-Regular', 'ui-monospace', 'Menlo', 'monospace'],
      },

      fontSize: {
        display: ['40px', { lineHeight: '1.15' }],
        h1: ['30px', { lineHeight: '1.15' }],
        h2: ['24px', { lineHeight: '1.3' }],
        h3: ['20px', { lineHeight: '1.3' }],
        h4: ['16px', { lineHeight: '1.3' }],
        'body-lg': ['16px', { lineHeight: '1.5' }],
        body: ['14px', { lineHeight: '1.5' }],
        'body-sm': ['13px', { lineHeight: '1.5' }],
        caption: ['12px', { lineHeight: '1.3' }],
        micro: ['11px', { lineHeight: '1.3', letterSpacing: '0.12em' }],
        mono: ['13px', { lineHeight: '1.5', letterSpacing: '0.01em' }],
        'mono-sm': ['12px', { lineHeight: '1.5', letterSpacing: '0.01em' }],
        'mono-lg': ['14px', { lineHeight: '1.5', letterSpacing: '0.01em' }],
      },

      fontWeight: {
        regular: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
      },

      letterSpacing: {
        tight: '-0.02em',
        normal: '0',
        wide: '0.02em',
        eyebrow: '0.12em',
        mono: '0.01em',
      },

      // ---- Spacing scale (4px base grid) ----
      spacing: {
        '0': '0',
        '1': '2px',
        '2': '4px',
        '3': '6px',
        '4': '8px',
        '5': '12px',
        '6': '16px',
        '7': '20px',
        '8': '24px',
        '9': '32px',
        '10': '40px',
        '11': '48px',
        '12': '64px',
        '13': '80px',
        // ---- Layout dimensions ----
        sidebar: '260px',
        'context-panel': '400px',
        header: '56px',
        composer: '88px',
        'max-readable': '720px',
      },

      borderRadius: {
        xs: '3px',
        sm: '5px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        pill: '999px',
      },

      borderWidth: {
        hairline: '1px',
        strong: '1.5px',
      },

      boxShadow: {
        // elevation
        'elev-1': '0 1px 2px rgba(0, 0, 0, 0.40)',
        'elev-2': '0 4px 12px rgba(0, 0, 0, 0.45)',
        'elev-3': '0 12px 32px rgba(0, 0, 0, 0.55)',
        popover: '0 8px 28px rgba(0, 0, 0, 0.60), 0 0 0 1px var(--border-default)',
        // glow (tech accent — small area)
        'glow-accent': '0 0 0 1px var(--accent-border), 0 0 16px var(--accent-glow)',
        'glow-accent-sm': '0 0 10px var(--accent-glow)',
        'glow-planning': '0 0 14px var(--route-planning-glow)',
        'glow-scheduling': '0 0 14px var(--route-scheduling-glow)',
        'glow-query': '0 0 14px var(--route-query-glow)',
        'glow-uncertain': '0 0 14px var(--route-uncertain-glow)',
        'glow-success': '0 0 14px rgba(44, 197, 111, 0.35)',
        'glow-confirm': '0 0 14px rgba(245, 158, 11, 0.35)',
        // inner top hairline highlight
        'inset-top-hi': 'inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        // focus ring
        focus: '0 0 0 2px #0A0E16, 0 0 0 4px var(--accent-border)',
      },

      backdropBlur: {
        glass: '14px',
      },

      transitionTimingFunction: {
        out: 'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-out': 'cubic-bezier(0.65, 0, 0.35, 1)',
      },

      transitionDuration: {
        fast: '120ms',
        normal: '200ms',
        slow: '320ms',
      },
    },
  },
  plugins: [],
};

export default config;
