export type SectionKey = 'llm' | 'embedding';

export interface Provider {
  id?: string;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
}

export interface ProvidersConfig {
  llm: { providers: Provider[]; active_id: string | null };
  embedding: { providers: Provider[]; active_id: string | null };
}

export const EMPTY_CONFIG: ProvidersConfig = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

export const EMPTY_PROVIDER: Provider = { name: '', base_url: '', api_key: '', model: '' };
