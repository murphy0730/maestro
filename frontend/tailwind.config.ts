import type { Config } from 'tailwindcss';

/**
 * Maestro design tokens — Linear/Vercel restyle.
 * The CSS custom properties live in src/index.css (light = :root default,
 * dark = [data-theme='dark'] overrides); this file mirrors them as semantic
 * Tailwind utilities for Runtime UI semantic tokens.
 *
 * Every color references its CSS var so hues can differ per theme — no
 * raw hex here. Source of truth for the raw values is index.css, which in
 * turn tracks docs/design/maestro-design-system-v1.html.
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

        // ---- Borders / hairlines ----
        'border-subtle': 'var(--border-subtle)',
        'border-default': 'var(--border-default)',
        'border-strong': 'var(--border-strong)',
        'border-accent': 'var(--border-accent)',

        // ============================================================
        // STATUS — feedback states
        // ============================================================
        status: {
          success: 'var(--status-success)',
          'success-bg': 'var(--status-success-bg)',
          warning: 'var(--status-warning)',
          'warning-bg': 'var(--status-warning-bg)',
          error: 'var(--status-error)',
          'error-bg': 'var(--status-error-bg)',
          info: 'var(--status-info)',
          'info-bg': 'var(--status-info-bg)',
        },

        // ============================================================
        // ACTION AUTHORIZATION — auto (green) vs confirm (amber)
        // ============================================================
        auth: {
          auto: 'var(--auth-auto)',
          'auto-bg': 'var(--auth-auto-bg)',
          'auto-border': 'var(--auth-auto-border)',
          confirm: 'var(--auth-confirm)',
          'confirm-bg': 'var(--auth-confirm-bg)',
          'confirm-border': 'var(--auth-confirm-border)',
        },

        // ============================================================
        // ACCENT — brand cyan (focus / highlights / live indicators)
        // ============================================================
        accent: {
          DEFAULT: 'var(--accent)',
          strong: 'var(--accent-strong)',
          fg: 'var(--accent-fg)',
          bg: 'var(--accent-bg)',
          border: 'var(--accent-border)',
        },

        // ============================================================
        // SOLID FILLS — filled controls carry white text on both themes.
        // blue = 沟通与导航 (send / new chat / my bubble)
        // green = successful execution
        // ============================================================
        'blue-solid': 'var(--blue-solid)',
        'blue-solid-hover': 'var(--blue-solid-hover)',
        'green-solid': 'var(--green-solid)',
        'green-solid-hover': 'var(--green-solid-hover)',
        'on-solid': 'var(--on-solid)',

        // ---- Data-viz sequence ----
        'data-1': 'var(--data-1)',
        'data-2': 'var(--data-2)',
        'data-3': 'var(--data-3)',
        'data-4': 'var(--data-4)',
        'data-5': 'var(--data-5)',
        'data-6': 'var(--data-6)',
      },

      // Geist carries headings, Inter carries prose, Geist Mono carries any
      // digits that must line up. Stacks are declared once in index.css.
      fontFamily: {
        display: 'var(--font-display)',
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
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
        sidebar: '228px',
        'context-panel': '400px',
        header: '56px',
        composer: '88px',
        'max-readable': '720px',
        // standard control height (buttons, inputs)
        control: '32px',
      },

      // ---- Radii — tightened from macOS 10/14/20. The geometric feel of
      // this language comes from the smaller curvature radius. ----
      borderRadius: {
        xs: '4px',
        sm: '6px',
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
        // elevation — restrained; hierarchy is carried by 1px hairlines
        'elev-1': 'var(--shadow-elev-1)',
        'elev-2': 'var(--shadow-elev-2)',
        'elev-3': 'var(--shadow-elev-3)',
        popover: 'var(--shadow-popover)',
        // Each glow resolves to a restrained hairline ring.
        'glow-accent': '0 0 0 1px var(--accent-border)',
        'glow-accent-sm': '0 0 0 1px var(--accent-border)',
        'glow-success': '0 0 0 1px var(--auth-auto-border)',
        'glow-confirm': '0 0 0 1px var(--auth-confirm-border)',
        // inner top hairline highlight (per-theme via CSS var)
        'inset-top-hi': 'inset 0 1px 0 var(--inset-hi)',
        // focus ring
        focus: '0 0 0 2px var(--bg-base), 0 0 0 4px var(--accent-border)',
      },

      // Retained so `backdrop-blur-glass` still compiles; the material is gone.
      backdropBlur: {
        glass: '0px',
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
