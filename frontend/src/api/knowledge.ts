import type {
  KnowledgeDeleteResponse,
  KnowledgeDoc,
  KnowledgeListResponse,
} from '@/types';
import { apiDelete, apiGet, apiUpload, type UploadOptions } from './client';

/** `GET /knowledge` — list all knowledge-base documents (查). */
export function listKnowledge(signal?: AbortSignal): Promise<KnowledgeListResponse> {
  return apiGet<KnowledgeListResponse>('/knowledge', { signal });
}

/** `POST /knowledge` — upload a file into the knowledge base (增). */
export function uploadKnowledge(file: File, opts?: UploadOptions): Promise<KnowledgeDoc> {
  const form = new FormData();
  form.append('file', file);
  return apiUpload<KnowledgeDoc>('/knowledge', form, 'POST', opts);
}

/** `PUT /knowledge/{id}` with a file — replace a document's content (改). */
export function replaceKnowledge(
  docId: string,
  file: File,
  opts?: UploadOptions,
): Promise<KnowledgeDoc> {
  const form = new FormData();
  form.append('file', file);
  return apiUpload<KnowledgeDoc>(`/knowledge/${docId}`, form, 'PUT', opts);
}

/** `PUT /knowledge/{id}` with a name — rename a document (改). */
export function renameKnowledge(docId: string, name: string): Promise<KnowledgeDoc> {
  const form = new FormData();
  form.append('name', name);
  return apiUpload<KnowledgeDoc>(`/knowledge/${docId}`, form, 'PUT');
}

/** `DELETE /knowledge/{id}` — remove a document and its vectors (删). */
export function deleteKnowledge(docId: string): Promise<KnowledgeDeleteResponse> {
  return apiDelete<KnowledgeDeleteResponse>(`/knowledge/${docId}`);
}
