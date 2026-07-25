import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SessionSidebar } from './SessionSidebar';

const sessions = [
  { session_id: 's1', title: '华东排产', updated_at: '2026-07-25T10:00:00Z', message_count: 3 },
  { session_id: 's2', title: '夜班分析', updated_at: '2026-07-24T10:00:00Z', message_count: 2 },
];

describe('SessionSidebar', () => {
  afterEach(cleanup);

  it('filters real sessions and switches the selected session', () => {
    const onSelect = vi.fn();
    render(<SessionSidebar sessions={sessions} activeSessionId="s1" collapsed={false} onCollapsedChange={vi.fn()} onCreate={vi.fn()} onSelect={onSelect} onRename={vi.fn()} onDelete={vi.fn()} onOpenSkills={vi.fn()} onOpenSettings={vi.fn()} onToggleTheme={vi.fn()} theme="dark" />);
    fireEvent.change(screen.getByPlaceholderText('搜索会话…'), { target: { value: '夜班' } });
    expect(screen.queryByText('华东排产')).toBeNull();
    fireEvent.click(screen.getByText('夜班分析'));
    expect(onSelect).toHaveBeenCalledWith('s2');
  });

  it('marks the active session and shows a real timestamp per row', () => {
    render(<SessionSidebar sessions={sessions} activeSessionId="s1" collapsed={false} onCollapsedChange={vi.fn()} onCreate={vi.fn()} onSelect={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} onOpenSkills={vi.fn()} onOpenSettings={vi.fn()} onToggleTheme={vi.fn()} theme="dark" />);
    const active = screen.getByRole('button', { name: '华东排产' });
    expect(active.getAttribute('aria-current')).toBe('true');
    // 消息条数没有独立视觉位，只经由 title 暴露，不伪造预览字段。
    expect(active.getAttribute('title')).toContain('3 条消息');
    expect(screen.getByRole('button', { name: '夜班分析' }).getAttribute('aria-current')).toBeNull();
    const row = active.closest('div');
    expect(row?.className).toContain('edge-marker');
    expect(row?.textContent).toMatch(/\d/);
  });

  it('renders the 56px rail actions when collapsed', () => {
    render(<SessionSidebar sessions={sessions} activeSessionId="s1" collapsed onCollapsedChange={vi.fn()} onCreate={vi.fn()} onSelect={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} onOpenSkills={vi.fn()} onOpenSettings={vi.fn()} onToggleTheme={vi.fn()} theme="dark" />);
    expect(screen.getByRole('button', { name: '展开会话栏' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '新建会话' })).toBeTruthy();
  });

  it('creates, renames and requests deletion through explicit controls', () => {
    const onCreate = vi.fn();
    const onRename = vi.fn();
    const onDelete = vi.fn();
    render(<SessionSidebar sessions={sessions} activeSessionId="s1" collapsed={false} onCollapsedChange={vi.fn()} onCreate={onCreate} onSelect={vi.fn()} onRename={onRename} onDelete={onDelete} onOpenSkills={vi.fn()} onOpenSettings={vi.fn()} onToggleTheme={vi.fn()} theme="dark" />);
    fireEvent.click(screen.getByRole('button', { name: '新建会话' }));
    expect(onCreate).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: '重命名 华东排产' }));
    fireEvent.change(screen.getByLabelText('会话标题'), { target: { value: '华东排产更新' } });
    fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
    expect(onRename).toHaveBeenCalledWith('s1', '华东排产更新');
    fireEvent.click(screen.getByRole('button', { name: '删除 华东排产' }));
    expect(onDelete).toHaveBeenCalledWith('s1');
  });
});
