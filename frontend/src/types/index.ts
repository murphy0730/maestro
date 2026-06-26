/**
 * Shared TypeScript types. Engine route classification mirrors the four
 * design-token families (see tailwind.config.ts). Extend as features land.
 */
export type RouteEngine = 'planning' | 'scheduling' | 'query' | 'uncertain';

export type AuthLevel = 'auto' | 'confirm';

export type StatusKind = 'success' | 'warning' | 'error' | 'info';
