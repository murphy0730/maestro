import { API_BASE, ApiError, authHeaders } from './client';
import type { ArtifactUpload } from '@/types/api/runs';

export async function uploadArtifact(file: File): Promise<ArtifactUpload> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/artifacts`, { method: 'POST', headers: authHeaders(), body: form });
  if (!response.ok) throw new ApiError(response.status, { code: 'ARTIFACT_UPLOAD_FAILED', message: response.statusText });
  return response.json() as Promise<ArtifactUpload>;
}
