import type { SkillMeta } from '@/types';
import type { SkillContextData } from '@/stores/conversationStore';

/** Resolve an untrusted-script observation to the exact installed skill version. */
export function findSkillTrustPrompt(
  skills: SkillMeta[],
  context: SkillContextData,
): SkillMeta | null {
  const blockedStep = [...context.steps].reverse().find((step) => {
    const blocked = step.observation?.blocked;
    return typeof blocked === 'string' && blocked.includes('未被本地用户信任');
  });
  const packageSha256 = blockedStep?.observation?.package_sha256;
  if (typeof packageSha256 !== 'string') return null;
  return (
    skills.find(
      (skill) =>
        !skill.trust?.valid &&
        skill.package_sha256 === packageSha256 &&
        (context.skillNames.length === 0 || context.skillNames.includes(skill.name)),
    ) ?? null
  );
}
