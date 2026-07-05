import type { SkillListResponse, SkillMeta } from '@/types';
import { apiDelete, apiGet, apiUpload } from './client';

/** `GET /skills` — list all registered skill packages (查). */
export function listSkills(): Promise<SkillListResponse> {
  return apiGet<SkillListResponse>('/skills');
}

/** `POST /skills/import` — upload a skill bundle .zip/.md file (增). */
export function importSkill(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<SkillMeta> {
  const form = new FormData();
  form.append('file', file);
  return apiUpload<SkillMeta>('/skills/import', form, 'POST', { onProgress });
}

/** `DELETE /skills/{name}` — remove a skill package (删). */
export function deleteSkill(name: string): Promise<void> {
  return apiDelete<void>(`/skills/${encodeURIComponent(name)}`);
}
