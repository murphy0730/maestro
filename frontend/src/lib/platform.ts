/**
 * Platform detection for window-chrome decisions. Computed once at module
 * load — plain constants, safe to import from presentational components.
 *
 * `window.electronAPI` is exposed by electron/preload.cjs (contextBridge);
 * it is undefined in the plain browser build, so both flags are `false` there.
 */
export const isElectron =
  typeof window !== 'undefined' && !!window.electronAPI?.isElectron;

/** True only in the Electron shell on macOS — gates hiddenInset titlebar
 *  affordances (drag regions, traffic-light inset). */
export const isMacDesktop = isElectron && window.electronAPI?.platform === 'darwin';
