import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SkillMenu } from './SkillMenu';
import { SKILLS } from '@/mocks/api/fixtures';

afterEach(cleanup);

const props = (overrides: Record<string, unknown> = {}) => ({
  skills: SKILLS,
  selected: [] as typeof SKILLS,
  onToggleSkill: vi.fn(),
  onClear: vi.fn(),
  onImportSkill: vi.fn(),
  open: true,
  onToggle: vi.fn(),
  ...overrides,
});

describe('SkillMenu', () => {
  it('lists skills and filters by search', () => {
    render(<SkillMenu {...props()} />);
    expect(screen.getByText('产能日报')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/搜索/), {
      target: { value: '换线' },
    });
    expect(screen.queryByText('产能日报')).toBeNull();
    expect(screen.getByText('换线检查清单')).toBeTruthy();
  });

  it('点击技能触发 onToggleSkill（不关闭菜单）', () => {
    const onToggleSkill = vi.fn();
    render(<SkillMenu {...props({ onToggleSkill })} />);
    fireEvent.click(screen.getByText('产能日报'));
    expect(onToggleSkill).toHaveBeenCalledWith(expect.objectContaining({ name: 'capacity-report' }));
  });

  it('清空与导入入口', () => {
    const onClear = vi.fn();
    const onImportSkill = vi.fn();
    render(<SkillMenu {...props({ onClear, onImportSkill, selected: [SKILLS[0]] })} />);
    fireEvent.click(screen.getByText(/清空/));
    expect(onClear).toHaveBeenCalled();
    fireEvent.click(screen.getByText(/导入技能/));
    expect(onImportSkill).toHaveBeenCalled();
  });
});
