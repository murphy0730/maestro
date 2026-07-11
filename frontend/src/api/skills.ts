import type {
  SkillListResponse,
  SkillMeta,
  SkillTrustStatus,
  SkillValidationReport,
} from '@/types';
import { apiDelete, apiGet, apiPost, apiUpload } from './client';

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

/** `POST /skills/validate` — compatibility preflight without persistence. */
export function validateSkill(file: File): Promise<SkillValidationReport> {
  const form = new FormData();
  form.append('file', file);
  return apiUpload<SkillValidationReport>('/skills/validate', form);
}

export function trustSkill(name: string, packageSha256: string): Promise<SkillTrustStatus> {
  return apiPost<SkillTrustStatus>(`/skills/${encodeURIComponent(name)}/trust`, {
    package_sha256: packageSha256,
    acknowledged_script_execution: true,
  });
}

export function revokeSkillTrust(name: string): Promise<SkillTrustStatus> {
  return apiDelete<SkillTrustStatus>(`/skills/${encodeURIComponent(name)}/trust`);
}

/** `DELETE /skills/{name}` — remove a skill package (删). */
export function deleteSkill(name: string): Promise<void> {
  return apiDelete<void>(`/skills/${encodeURIComponent(name)}`);
}
