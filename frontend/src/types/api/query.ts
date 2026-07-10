import type { ApiErrorResponse } from './shared';

export interface QueryStreamRequest {
  session_id: string;
  question: string;
}

export interface RagSource {
  id: string;
  doc_name: string;
  section: string;
  snippet: string;
  relevance: number;
}

export type QueryStreamEvent =
  | { event: 'token'; data: { delta: string } }
  | { event: 'sources'; data: { sources: RagSource[] } }
  | { event: 'done'; data: { message_id: string } }
  | { event: 'error'; data: ApiErrorResponse };

export type KnowledgeDocStatus = 'ready' | 'failed';

export interface KnowledgeDoc {
  doc_id: string;
  name: string;
  type: string;
  chunk_count: number;
  bytes: number;
  status: KnowledgeDocStatus;
  added_at: string;
}

export interface KnowledgeListResponse {
  docs: KnowledgeDoc[];
  supported_extensions: string[];
}

export interface KnowledgeDeleteResponse {
  doc_id: string;
  removed_chunks: number;
}
