import { ApiError } from '@/api/client';

/* Shared non-component helpers for the knowledge-base panel. */

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function extOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot).toLowerCase() : '';
}

export function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return '操作失败';
}

/** An in-flight upload (new file) with its live progress. */
export interface UploadTask {
  id: string;
  name: string;
  fraction: number;
  error?: string;
}
