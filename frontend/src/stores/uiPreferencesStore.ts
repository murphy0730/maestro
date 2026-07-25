import { create } from 'zustand';

export type RunMode = 'auto' | 'planning' | 'scheduling' | 'query';
export type TraceDefault = 'docked' | 'hidden';

interface UiPreferences {
  sidebarCollapsed: boolean;
  reducedMotion: boolean;
  defaultMode: RunMode;
  traceDefault: TraceDefault;
}

interface UiPreferencesStore extends UiPreferences {
  setSidebarCollapsed: (collapsed: boolean) => void;
  setReducedMotion: (reduced: boolean) => void;
  setDefaultMode: (mode: RunMode) => void;
  setTraceDefault: (state: TraceDefault) => void;
}

const STORAGE_KEY = 'maestro-ui-preferences';
const defaults: UiPreferences = {
  sidebarCollapsed: false,
  reducedMotion: false,
  defaultMode: 'auto',
  traceDefault: 'docked',
};

function readInitial(): UiPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<UiPreferences>;
    return { ...defaults, ...saved };
  } catch {
    return defaults;
  }
}

function persist(value: UiPreferences) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  document.documentElement.dataset.reducedMotion = String(value.reducedMotion);
}

export const useUiPreferencesStore = create<UiPreferencesStore>((set) => {
  const initial = readInitial();
  document.documentElement.dataset.reducedMotion = String(initial.reducedMotion);
  const update = (patch: Partial<UiPreferences>) =>
    set((state) => {
      const next = { ...state, ...patch } as UiPreferencesStore;
      persist(next);
      return patch;
    });
  return {
    ...initial,
    setSidebarCollapsed: (sidebarCollapsed) => update({ sidebarCollapsed }),
    setReducedMotion: (reducedMotion) => update({ reducedMotion }),
    setDefaultMode: (defaultMode) => update({ defaultMode }),
    setTraceDefault: (traceDefault) => update({ traceDefault }),
  };
});
