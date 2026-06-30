import type { StatusKind } from '@/types';

/** Static Tailwind class strings per status tone (token-driven, no hex). */
export const STATUS_CLASSES: Record<StatusKind, { text: string; bg: string; dot: string }> = {
  success: { text: 'text-status-success', bg: 'bg-status-success-bg', dot: 'bg-status-success' },
  warning: { text: 'text-status-warning', bg: 'bg-status-warning-bg', dot: 'bg-status-warning' },
  error: { text: 'text-status-error', bg: 'bg-status-error-bg', dot: 'bg-status-error' },
  info: { text: 'text-status-info', bg: 'bg-status-info-bg', dot: 'bg-status-info' },
};
