import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Composer } from './Composer';
import type { SkillMeta } from '@/types';

afterEach(cleanup);

const selectedSkill = {
  name: 'capacity-report',
  display_name: '产能日报',
} as SkillMeta;

const props = (overrides: Record<string, unknown> = {}) => ({
  onSend: vi.fn(),
  expert: false,
  onExpertChange: vi.fn(),
  skills: [selectedSkill],
  selectedSkills: [selectedSkill],
  onToggleSkill: vi.fn(),
  onClearSkills: vi.fn(),
  onImportSkill: vi.fn(),
  ...overrides,
});

describe('Composer', () => {
  it('会话尚未就绪时禁止发送消息', () => {
    const onSend = vi.fn();
    render(<Composer {...props({ onSend, disabled: true })} />);

    const input = screen.getByPlaceholderText('正在加载会话…');
    expect((input as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('发送消息'));

    expect(onSend).not.toHaveBeenCalled();
  });

  it('输入法组合期间按 Enter 不发送消息', () => {
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);
    const input = screen.getByPlaceholderText(/描述要完成/);

    fireEvent.change(input, { target: { value: '中文' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });

    expect(onSend).not.toHaveBeenCalled();
    expect((input as HTMLTextAreaElement).value).toBe('中文');
  });

  it('发送后清空文本、附件和已选技能', async () => {
    const onSend = vi.fn();
    const onClearSkills = vi.fn();
    const { container } = render(<Composer {...props({ onSend, onClearSkills })} />);
    const input = screen.getByPlaceholderText(/描述要完成/);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '分析附件' } });
    fireEvent.change(fileInput, {
      target: { files: [new File(['data'], 'report.csv', { type: 'text/csv' })] },
    });
    expect(await screen.findByText('report.csv')).toBeTruthy();

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onSend).toHaveBeenCalledWith(
      '分析附件',
      expect.arrayContaining([expect.objectContaining({ name: 'report.csv' })]),
    );
    expect(onClearSkills).toHaveBeenCalledOnce();
    expect((input as HTMLTextAreaElement).value).toBe('');
    expect(screen.queryByText('report.csv')).toBeNull();
  });
});
