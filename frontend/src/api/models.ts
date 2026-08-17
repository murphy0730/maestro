import type { ModelsConfig, ModelsSaveResult, ModelTestInput, ModelTestResult } from '@/types';
import { apiGet, apiPost, apiPut } from './client';

/** `GET /models` — read-only; `api_key` always comes back empty. */
export function getModels(): Promise<ModelsConfig> {
  return apiGet<ModelsConfig>('/models');
}

/**
 * `PUT /models` — persist and hot-reload the running client.
 * Host administration: needs `VITE_PRIVILEGED_API_TOKEN`, else 403.
 * A blank `api_key` on an existing entry keeps the stored one.
 */
export function saveModels(config: ModelsConfig): Promise<ModelsSaveResult> {
  return apiPut<ModelsSaveResult>('/models', config);
}

/**
 * `POST /models/test` — probe a candidate connection without touching the live client.
 * Host administration: needs `VITE_PRIVILEGED_API_TOKEN`, else 403.
 */
export function testModelProvider(input: ModelTestInput): Promise<ModelTestResult> {
  return apiPost<ModelTestResult>('/models/test', input);
}
