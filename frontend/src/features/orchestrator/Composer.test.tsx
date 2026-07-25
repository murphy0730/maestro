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

  it('文本为空时发送按钮保持禁用', () => {
    render(<Composer {...props()} />);
    expect((screen.getByLabelText('发送消息') as HTMLButtonElement).disabled).toBe(true);
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

  it('Shift+Enter inserts a newline without sending', () => {
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);
    const input = screen.getByPlaceholderText(/描述要完成/);
    fireEvent.change(input, { target: { value: '第一行' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('does not silently submit a backend-unsupported direct mode', () => {
    const onSend = vi.fn();
    render(<Composer {...props({ onSend, mode: 'planning', onModeChange: vi.fn() })} />);
    fireEvent.change(screen.getByPlaceholderText(/描述要完成/), { target: { value: '排产' } });
    fireEvent.click(screen.getByLabelText('发送消息'));
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('后端暂不支持');
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

  it('同名附件使用最新文件且可移除', () => {
    const { container } = render(<Composer {...props()} />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['old'], 'report.csv')] } });
    fireEvent.change(fileInput, { target: { files: [new File(['new'], 'report.csv')] } });
    expect(screen.getAllByText('report.csv')).toHaveLength(1);
    fireEvent.click(screen.getByTitle('移除附件'));
    expect(screen.queryByText('report.csv')).toBeNull();
  });

  it('拒绝超过 10 MB 的附件并显示可恢复错误', () => {
    const { container } = render(<Composer {...props()} />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.bin')] } });
    expect(screen.getByRole('alert').textContent).toContain('10 MB');
    expect(screen.queryByText('large.bin')).toBeNull();
  });

  it('异步发送失败后保留草稿、附件和技能供重试', async () => {
    const onSend = vi.fn().mockRejectedValue(new Error('network'));
    const onClearSkills = vi.fn();
    const { container } = render(<Composer {...props({ onSend, onClearSkills })} />);
    const input = screen.getByPlaceholderText(/描述要完成/);
    fireEvent.change(input, { target: { value: '保留我' } });
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [new File(['x'], 'retry.txt')] } });
    fireEvent.click(screen.getByLabelText('发送消息'));
    await vi.waitFor(() => expect((input as HTMLTextAreaElement).disabled).toBe(false));
    expect((input as HTMLTextAreaElement).value).toBe('保留我');
    expect(screen.getByText('retry.txt')).toBeTruthy();
    expect(onClearSkills).not.toHaveBeenCalled();
  });
});
