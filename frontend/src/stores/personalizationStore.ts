import { create } from 'zustand';

const STORAGE_KEY = 'maestro-personalization';

export interface Personalization {
  /** 如何称呼用户，例如「周工」「老板」。 */
  howToAddress: string;
  /** 用户对助手的要求 / 偏好，自由文本。 */
  requirements: string;
  /** 语气 / 风格：默认、专业、简洁、友好。 */
  tone: 'default' | 'professional' | 'concise' | 'friendly';
}

const DEFAULTS: Personalization = {
  howToAddress: '',
  requirements: '',
  tone: 'default',
};

function readInitial(): Personalization {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Personalization>) };
  } catch {
    return { ...DEFAULTS };
  }
}

interface PersonalizationStoreState {
  data: Personalization;
  update: (patch: Partial<Personalization>) => void;
  reset: () => void;
}

export const usePersonalizationStore = create<PersonalizationStoreState>((set) => {
  const initial = readInitial();
  return {
    data: initial,
    update: (patch) =>
      set((s) => {
        const next = { ...s.data, ...patch };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return { data: next };
      }),
    reset: () => {
      localStorage.removeItem(STORAGE_KEY);
      set({ data: { ...DEFAULTS } });
    },
  };
});
