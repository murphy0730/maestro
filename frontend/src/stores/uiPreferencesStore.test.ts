import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('uiPreferencesStore', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-reduced-motion');
    vi.resetModules();
  });

  it('persists sidebar, trace and mode preferences', async () => {
    const { useUiPreferencesStore } = await import('./uiPreferencesStore');
    const store = useUiPreferencesStore.getState();
    store.setSidebarCollapsed(true);
    store.setTraceDefault('hidden');
    store.setDefaultMode('query');
    const saved = JSON.parse(localStorage.getItem('maestro-ui-preferences') ?? '{}');
    expect(saved).toMatchObject({ sidebarCollapsed: true, traceDefault: 'hidden', defaultMode: 'query' });
  });

  it('marks the document when reduced motion is enabled', async () => {
    const { useUiPreferencesStore } = await import('./uiPreferencesStore');
    useUiPreferencesStore.getState().setReducedMotion(true);
    expect(document.documentElement.dataset.reducedMotion).toBe('true');
  });
});
