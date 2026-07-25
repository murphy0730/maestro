import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    vi.resetModules();
  });

  it('uses deep-field dark as the default theme', async () => {
    const { useThemeStore } = await import('./themeStore');
    expect(useThemeStore.getState().theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('persists daylight and applies it to the document', async () => {
    const { useThemeStore } = await import('./themeStore');
    useThemeStore.getState().setTheme('light');
    expect(localStorage.getItem('maestro-theme')).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
