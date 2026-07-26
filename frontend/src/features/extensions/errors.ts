import { ApiError } from '@/api';

/** 403 means the privileged token is missing or mismatched — say so plainly. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return '需要扩展管理凭证：前后端的 PRIVILEGED_API_TOKEN 必须一致，改后需重启后端。';
  }
  return error instanceof Error && error.message ? error.message : '操作失败';
}
