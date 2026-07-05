import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SkillMenu } from './SkillMenu';
import { SKILLS } from '@/mocks/api/fixtures';

afterEach(cleanup);

const props = (overrides: Record<string, unknown> = {}) => ({
  skills: SKILLS,
  skill: null,
  onSkillChange: vi.fn(),
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

  it('selecting a skill calls onSkillChange', () => {
    const onChange = vi.fn();
    render(<SkillMenu {...props({ onSkillChange: onChange })} />);
    fireEvent.click(screen.getByText('产能日报'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'capacity-report' }),
    );
  });

  it('clear and import entries', () => {
    const onSkillChange = vi.fn();
    const onImportSkill = vi.fn();
    render(<SkillMenu {...props({ onSkillChange, onImportSkill })} />);
    fireEvent.click(screen.getByText('不使用技能'));
    expect(onSkillChange).toHaveBeenCalledWith(null);
    fireEvent.click(screen.getByText(/导入技能/));
    expect(onImportSkill).toHaveBeenCalled();
  });
});
