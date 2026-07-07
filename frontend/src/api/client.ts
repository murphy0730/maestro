import type { ApiErrorBody, ApiErrorResponse } from '@/types';

/** API base URL + version prefix. Same-origin by default so MSW can intercept. */
function resolveApiBase(): string {
  // 打包后 Electron 经 URL 查询参数 bp 注入动态端口 (?bp=<port>)；
  // dev (Vite 代理) 与浏览器回落到 VITE_API_BASE_URL / /api/v1。
  if (typeof window !== 'undefined') {
    const bp = new URLSearchParams(window.location.search).get('bp');
    if (bp) return `http://127.0.0.1:${bp}`;
  }
  return import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
}
export const API_BASE = resolveApiBase();

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

/** FastAPI HTTPException shape: `{ "detail": "message" }`. */
function detailMessage(body: unknown): string | undefined {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
  }
  return undefined;
}

/** Map either the contract envelope or FastAPI's `{detail}` into an ApiError. */
function bodyToApiError(status: number, statusText: string, body: unknown): ApiError {
  if (isErrorResponse(body)) return new ApiError(status, body.error);
  const detail = detailMessage(body);
  if (detail) return new ApiError(status, { code: 'HTTP_ERROR', message: detail });
  return new ApiError(status, { code: 'HTTP_ERROR', message: `${status} ${statusText}` });
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  return bodyToApiError(res.status, res.statusText, body);
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
export async function apiPost<T>(
  path: string,
  body: unknown,
  opts: RequestOptions = {},
): Promise<T> {
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
export async function apiPatch<T>(
  path: string,
  body: unknown,
  opts: RequestOptions = {},
): Promise<T> {
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

export interface UploadOptions extends RequestOptions {
  /** Upload progress 0–1 (fired repeatedly as bytes flush). */
  onProgress?: (fraction: number) => void;
}

/**
 * multipart/form-data upload via XMLHttpRequest — `fetch` cannot report upload
 * progress, so we use XHR to drive the progress bar. Do NOT set Content-Type;
 * the browser adds the multipart boundary. Throws {@link ApiError} on non-2xx.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  method: 'POST' | 'PUT' = 'POST',
  opts: UploadOptions = {},
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, `${API_BASE}${path}`);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.responseType = 'text';

    if (opts.onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) opts.onProgress!(e.loaded / e.total);
      };
    }

    const parseError = (): ApiError => {
      let body: unknown;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = undefined;
      }
      return bodyToApiError(xhr.status || 0, xhr.statusText, body);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        opts.onProgress?.(1);
        resolve((xhr.responseText ? JSON.parse(xhr.responseText) : undefined) as T);
      } else {
        reject(parseError());
      }
    };
    xhr.onerror = () =>
      reject(new ApiError(0, { code: 'NETWORK_ERROR', message: '上传失败 (网络错误)' }));
    xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'));

    if (opts.signal) {
      if (opts.signal.aborted) return xhr.abort();
      opts.signal.addEventListener('abort', () => xhr.abort(), { once: true });
    }
    xhr.send(form);
  });
}

/** Build a full URL with query params, dropping null/undefined values. */
export function withQuery(
  path: string,
  params: Record<string, string | number | null | undefined>,
): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}
