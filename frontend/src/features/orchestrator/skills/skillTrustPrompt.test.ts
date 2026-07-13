import { describe, expect, it } from 'vitest';
import type { SkillMeta } from '@/types';
import { findSkillTrustPrompt } from './skillTrustPrompt';

const docx: SkillMeta = {
  name: 'docx',
  display_name: 'Word 文档',
  description: '创建 Word 文档',
  scripts: ['scripts/create.py'],
  file_count: 2,
  bytes: 200,
  added_at: '2026-07-13T00:00:00Z',
  package_sha256: 'docx-hash',
  trust: { level: 'untrusted', valid: false, package_sha256: 'docx-hash' },
};

describe('findSkillTrustPrompt', () => {
  it('matches an untrusted conversation result to the exact skill package', () => {
    expect(
      findSkillTrustPrompt([docx], {
        skillNames: ['docx'],
        steps: [
          {
            tool: 'run_skill_script',
            observation: {
              blocked: '技能当前版本尚未被本地用户信任，请先信任当前版本',
              package_sha256: 'docx-hash',
            },
          },
        ],
      }),
    ).toBe(docx);
  });

  it('does not prompt when the package hash does not match', () => {
    expect(
      findSkillTrustPrompt([docx], {
        skillNames: ['docx'],
        steps: [
          {
            tool: 'run_skill_script',
            observation: {
              blocked: '技能当前版本尚未被本地用户信任',
              package_sha256: 'older-hash',
            },
          },
        ],
      }),
    ).toBeNull();
  });
});
