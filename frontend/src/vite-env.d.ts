/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL + prefix. Defaults to `/api/v1` (same-origin / MSW). */
  readonly VITE_API_BASE_URL?: string;
  /** Set to `disabled` to turn off MSW request mocking in dev. */
  readonly VITE_API_MOCKING?: 'enabled' | 'disabled';
  /** Privileged token for skill / MCP administration; must match the backend. */
  readonly VITE_PRIVILEGED_API_TOKEN?: string;
  /**
   * `on` shows the Extensions Center browse views (推荐 / SkillHub / 可用连接器).
   * They render a local static catalog — there is no backend behind them yet.
   */
  readonly VITE_EXTENSION_CATALOG?: 'on' | 'off';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Bridge exposed by electron/preload.cjs; absent in the plain browser build. */
interface Window {
  electronAPI?: {
    isElectron: boolean;
    platform: string;
  };
}
