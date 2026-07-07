import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => window.history.replaceState({}, '', '/'));

describe('API_BASE resolution', () => {
  it('uses bp query param when present', async () => {
    vi.resetModules();
    window.history.replaceState({}, '', '/?bp=9123');
    const { API_BASE } = await import('./client');
    expect(API_BASE).toBe('http://127.0.0.1:9123');
  });

  it('falls back to /api/v1 when no bp and no VITE_API_BASE_URL', async () => {
    vi.resetModules();
    window.history.replaceState({}, '', '/');
    const { API_BASE } = await import('./client');
    expect(API_BASE).toBe('/api/v1');
  });
});
