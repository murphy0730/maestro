/**
 * Centralized TanStack Query keys. Keep all cache keys here so invalidation
 * stays consistent across hooks.
 */
export const queryKeys = {
  planning: {
    solveRuns: (sessionId: string) => ['planning', 'solve-runs', sessionId] as const,
  },
  scheduling: {
    kitting: (sessionId: string, scope?: string) => ['scheduling', 'kitting', sessionId, scope ?? null] as const,
    dispatchOrders: (sessionId: string) => ['scheduling', 'dispatch-orders', sessionId] as const,
    exceptionImpact: (sessionId: string, eventId: string) =>
      ['scheduling', 'exception-impact', sessionId, eventId] as const,
  },
  audit: {
    timeline: (sessionId: string) => ['audit', 'timeline', sessionId] as const,
  },
  knowledge: {
    list: () => ['knowledge', 'list'] as const,
  },
  skills: {
    list: () => ['skills', 'list'] as const,
  },
  extensions: {
    connectors: () => ['extensions', 'connectors', 'servers'] as const,
    catalog: (kind: 'skills' | 'connectors', q = '') => ['extensions', 'catalog', kind, q] as const,
    catalogStatus: () => ['extensions', 'catalog', 'status'] as const,
  },
  sessions: {
    list: () => ['sessions', 'list'] as const,
  },
} as const;
