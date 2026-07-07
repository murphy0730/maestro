import { create } from 'zustand';

export type DefaultEngine = 'auto' | 'planning' | 'scheduling' | 'query';

const STORAGE_KEY = 'maestro-default-engine';
const VALID: DefaultEngine[] = ['auto', 'planning', 'scheduling', 'query'];

/** 读取初始默认引擎：localStorage 优先，缺省 auto。 */
function readInitial(): DefaultEngine {
  const saved = localStorage.getItem(STORAGE_KEY) as DefaultEngine | null;
  return saved && VALID.includes(saved) ? saved : 'auto';
}

interface DefaultEngineState {
  defaultEngine: DefaultEngine;
  setDefaultEngine: (engine: DefaultEngine) => void;
}

export const useDefaultEngineStore = create<DefaultEngineState>((set) => ({
  defaultEngine: readInitial(),
  setDefaultEngine: (engine) => {
    localStorage.setItem(STORAGE_KEY, engine);
    set({ defaultEngine: engine });
  },
}));
