/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL + prefix. Defaults to `/api/v1` (same-origin / MSW). */
  readonly VITE_API_BASE_URL?: string;
  /** Set to `disabled` to turn off MSW request mocking in dev. */
  readonly VITE_API_MOCKING?: 'enabled' | 'disabled';
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
