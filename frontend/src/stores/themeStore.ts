import { create } from 'zustand';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'maestro-theme';

/** 读取初始主题：localStorage 优先，缺省为设计系统主场「深空」。 */
function readInitialTheme(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === 'light' ? 'light' : 'dark';
}

/** 把主题写到 <html data-theme>，驱动 index.css 的 token 覆盖。 */
function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

interface ThemeStoreState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

export const useThemeStore = create<ThemeStoreState>((set) => {
  const initial = readInitialTheme();
  applyTheme(initial);
  return {
    theme: initial,
    setTheme: (theme) => {
      localStorage.setItem(STORAGE_KEY, theme);
      applyTheme(theme);
      set({ theme });
    },
  };
});
