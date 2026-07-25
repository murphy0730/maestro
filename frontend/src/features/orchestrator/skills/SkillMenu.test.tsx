import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { SkillMeta } from '@/types';
import { SkillMenu } from './SkillMenu';

const skill = {
  name: 'quality',
  display_name: '质量分析',
  description: 'SPC',
  user_invocable: true,
  scripts: ['run.py'],
  file_count: 2,
  bytes: 12,
  added_at: '',
  package_sha256: 'sha',
  trust: { level: 'untrusted' as const, valid: false, package_sha256: 'sha' },
} satisfies SkillMeta;

afterEach(cleanup);

describe('SkillMenu', () => {
  it('searches, selects, clears, trusts and opens import through real callbacks', () => {
    const onToggleSkill = vi.fn();
    const onClear = vi.fn();
    const onTrustSkill = vi.fn();
    const onImportSkill = vi.fn();
    render(
      <SkillMenu
        open
        skills={[skill]}
        selected={[skill]}
        onToggleSkill={onToggleSkill}
        onClear={onClear}
        onImportSkill={onImportSkill}
        onTrustSkill={onTrustSkill}
      />,
    );
    fireEvent.change(screen.getByLabelText('搜索技能'), { target: { value: '质量' } });
    fireEvent.click(screen.getByRole('menuitemcheckbox'));
    expect(onToggleSkill).toHaveBeenCalledWith(skill);
    fireEvent.click(screen.getByRole('button', { name: '清空已选' }));
    expect(onClear).toHaveBeenCalled();
    fireEvent.click(screen.getByTitle('信任当前版本脚本'));
    expect(onTrustSkill).toHaveBeenCalledWith(skill);
    fireEvent.click(screen.getByRole('button', { name: '导入技能' }));
    expect(onImportSkill).toHaveBeenCalled();
  });
});
