/** Model provider administration — mirrors `docs/api-contract/agent-runtime-v1.md` §模型与引擎. */

export type ModelSectionKey = 'llm' | 'embedding';

export interface ModelProvider {
  /** Assigned by the client on creation; absent only for an unsaved draft. */
  id?: string;
  name: string;
  base_url: string;
  model: string;
  /** The backend never echoes the secret — this is always `''` on read. */
  api_key: string;
  /** Backend-derived: whether a key is actually stored for this entry. */
  api_key_set?: boolean;
}

export interface ModelProviderSection {
  providers: ModelProvider[];
  /** The entry whose connection the Runtime actually uses; `null` falls back to `.env`. */
  active_id: string | null;
}

export interface ModelsConfig {
  llm: ModelProviderSection;
  embedding: ModelProviderSection;
}

/** `PUT /models` additionally reports whether the live client came up. */
export interface ModelsSaveResult extends ModelsConfig {
  available: boolean;
}

export interface ModelTestInput {
  section: ModelSectionKey;
  /** Lets the backend reuse the stored key when testing a saved entry. */
  id?: string;
  base_url: string;
  model: string;
  api_key: string;
}

export interface ModelTestResult {
  ok: boolean;
  error: string;
  latency_ms: number;
}
