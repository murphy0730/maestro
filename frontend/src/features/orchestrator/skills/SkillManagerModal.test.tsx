import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { SkillMeta } from '@/types';

const mocks = vi.hoisted(() => ({ trustSkill: vi.fn(), revokeSkillTrust: vi.fn(), deleteSkill: vi.fn() }));
vi.mock('@/api', () => mocks);
import { SkillManagerModal } from './SkillManagerModal';

const base = { description: '测试技能', user_invocable: true, file_count: 1, bytes: 42, added_at: '2026-07-25T00:00:00Z', package_sha256: 'sha', compatibility_status: 'ready' as const };
const skills: SkillMeta[] = [
  { ...base, name: 'quality', display_name: '质量分析' },
  { ...base, name: 'planning', display_name: '排产专家', trust: { level: 'user_trusted', valid: true, package_sha256: 'sha' } },
];

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

describe('SkillManagerModal', () => {
  it('searches and refreshes after trust and revoke operations', async () => {
    mocks.trustSkill.mockResolvedValue({ level: 'user_trusted', valid: true });
    mocks.revokeSkillTrust.mockResolvedValue({ level: 'untrusted', valid: true });
    const onChanged = vi.fn();
    render(<SkillManagerModal open onClose={vi.fn()} skills={skills} loading={false} onImport={vi.fn()} onChanged={onChanged} />);
    fireEvent.change(screen.getByPlaceholderText('搜索技能…'), { target: { value: '质量' } });
    expect(screen.queryByText('排产专家')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '信任' }));
    await vi.waitFor(() => expect(mocks.trustSkill).toHaveBeenCalledWith('quality', true));
    expect(onChanged).toHaveBeenCalled();
  });

  it('revokes trust and deletes only after confirmation', async () => {
    mocks.revokeSkillTrust.mockResolvedValue({ level: 'untrusted', valid: true });
    mocks.deleteSkill.mockResolvedValue(undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<SkillManagerModal open onClose={vi.fn()} skills={[skills[1]]} loading={false} onImport={vi.fn()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '撤销信任' }));
    await vi.waitFor(() => expect(mocks.revokeSkillTrust).toHaveBeenCalledWith('planning'));
    const deleteButton = screen.getByRole('button', { name: '删除技能 planning' }) as HTMLButtonElement;
    await vi.waitFor(() => expect(deleteButton.disabled).toBe(false));
    fireEvent.click(deleteButton);
    await vi.waitFor(() => expect(mocks.deleteSkill).toHaveBeenCalledWith('planning'));
    expect(window.confirm).toHaveBeenCalled();
  });

  it('surfaces structured mutation failures', async () => {
    mocks.trustSkill.mockRejectedValue(new Error('需要管理员令牌'));
    render(<SkillManagerModal open onClose={vi.fn()} skills={[skills[0]]} loading={false} onImport={vi.fn()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '信任' }));
    expect((await screen.findByRole('alert')).textContent).toContain('需要管理员令牌');
  });
});
