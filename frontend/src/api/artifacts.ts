import { apiUpload } from './client';
import type { ArtifactUpload } from '@/types/api/runs';

export async function uploadArtifact(file: File): Promise<ArtifactUpload> {
  const form = new FormData();
  form.append('file', file);
  return apiUpload<ArtifactUpload>('/artifacts', form);
}
