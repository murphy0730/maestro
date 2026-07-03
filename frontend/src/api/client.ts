import type { ApiErrorBody, ApiErrorResponse } from '@/types';

/** API base URL + version prefix. Same-origin by default so MSW can intercept. */
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/** Thrown for any non-2xx response; carries the contract's structured error. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
  }
}

function isErrorResponse(value: unknown): value is ApiErrorResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorResponse).error?.code === 'string'
  );
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  if (isErrorResponse(body)) return new ApiError(res.status, body.error);
  return new ApiError(res.status, { code: 'HTTP_ERROR', message: `${res.status} ${res.statusText}` });
}

interface RequestOptions {
  signal?: AbortSignal;
}

/** JSON GET. Throws {@link ApiError} on non-2xx. */
export async function apiGet<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal: opts.signal,
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

/** JSON POST. Throws {@link ApiError} on non-2xx. */
export async function apiPost<T>(path: string, body: unknown, opts: RequestOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

/** JSON PATCH. Throws {@link ApiError} on non-2xx. */
export async function apiPatch<T>(path: string, body: unknown, opts: RequestOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

/** JSON DELETE. Throws {@link ApiError} on non-2xx. */
export async function apiDelete<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
    signal: opts.signal,
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

/** Build a full URL with query params, dropping null/undefined values. */
export function withQuery(path: string, params: Record<string, string | number | null | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}
