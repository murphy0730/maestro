/**
 * Vitest global setup.
 *
 * Node 25 exposes a native Web Storage `localStorage` global that shadows
 * jsdom's `window.localStorage` and throws ("getItem is not a function")
 * unless started with `--localstorage-file`. Store modules read localStorage
 * at import time (e.g. themeStore / defaultEngineStore call it inside the
 * zustand `create`), so a per-test mock in `beforeEach` runs too late. Install
 * a working in-memory Storage on both globals before any module loads.
 */
function makeStorage(): Storage {
  const m = new Map<string, string>();
  return {
    get length() {
      return m.size;
    },
    clear: () => m.clear(),
    getItem: (k: string) => (m.has(k) ? (m.get(k) as string) : null),
    key: (i: number) => [...m.keys()][i] ?? null,
    removeItem: (k: string) => {
      m.delete(k);
    },
    setItem: (k: string, v: string) => {
      m.set(k, String(v));
    },
  } as Storage;
}

const storage = makeStorage();
Object.defineProperty(globalThis, 'localStorage', {
  value: storage,
  configurable: true,
  writable: true,
});
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: storage,
    configurable: true,
    writable: true,
  });
}
