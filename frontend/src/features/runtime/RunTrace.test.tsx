import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunTrace } from './RunTrace';
const projection = { tokens: '', diagnostics: [], events: ['run.waiting_approval'], recovered: false, upgradeReason: 'write', run: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'structured' as const, status: 'waiting_approval' as const, steps: {}, final_text: null, revision: 2, pending_approvals: [{ approval_id: 'a1', step_id: 's1', impact_summary: '写入 MES', policy_reason: 'high risk', run_revision: 2, status: 'pending' as const }] } };
describe('RunTrace', () => {
  afterEach(cleanup);
  it('shows controlled execution and disables approval while in flight', () => {
    render(<RunTrace projection={projection} approvingId="a1" onApprove={vi.fn()} />);
    expect(screen.getByText('已升级为受控执行')).toBeTruthy(); expect(screen.getByText('等待确认')).toBeTruthy();
    expect((screen.getByRole('button', { name: '确认' }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('sends an approval choice', () => { const onApprove = vi.fn(); render(<RunTrace projection={projection} onApprove={onApprove} />); fireEvent.click(screen.getByRole('button', { name: '拒绝' })); expect(onApprove).toHaveBeenCalledWith(projection.run.pending_approvals[0], false); });
  it('does not call waiting external recovered', () => { render(<RunTrace projection={{ ...projection, run: { ...projection.run, status: 'waiting_external' } }} onApprove={vi.fn()} />); expect(screen.getByText('等待外部完成')).toBeTruthy(); expect(screen.queryByText('已恢复')).toBeNull(); });
  it('offers dock, hide and fullscreen controls', () => {
    const onViewChange = vi.fn();
    render(<RunTrace projection={projection} onApprove={vi.fn()} view="docked" onViewChange={onViewChange} />);
    fireEvent.click(screen.getByRole('button', { name: '全屏运行详情' }));
    expect(onViewChange).toHaveBeenCalledWith('fullscreen');
    fireEvent.click(screen.getByRole('button', { name: '隐藏运行详情' }));
    expect(onViewChange).toHaveBeenCalledWith('hidden');
  });
  it('renders a step timeline from the real snapshot steps', () => {
    const withSteps = { ...projection, run: { ...projection.run, steps: { s1: { step_id: 's1', kind: '拉取工单', status: 'succeeded' as const }, s2: { step_id: 's2', kind: '生成方案', status: 'running' as const } } } };
    const { container } = render(<RunTrace projection={withSteps} onApprove={vi.fn()} />);
    expect(screen.getByText('步骤 · 1/2')).toBeTruthy();
    expect(screen.getByText('拉取工单')).toBeTruthy();
    // 状态同时用文字表达，不只靠颜色。
    expect(screen.getByText('成功')).toBeTruthy();
    expect(screen.getByText('运行中')).toBeTruthy();
    expect(container.querySelectorAll('.step-timeline > li')).toHaveLength(2);
  });

  it('lays the fullscreen view out as steps beside the pending approval', () => {
    const { container } = render(<RunTrace projection={projection} onApprove={vi.fn()} view="fullscreen" onViewChange={vi.fn()} />);
    expect(screen.getByText('运行轨迹 · 全屏')).toBeTruthy();
    expect(screen.getByRole('button', { name: '还原驻留详情' })).toBeTruthy();
    expect(container.querySelector('.grid-cols-\\[1\\.1fr_\\.9fr\\]')).toBeTruthy();
    expect(screen.getByText('写入 MES')).toBeTruthy();
  });

  it('keeps revision conflicts and network failures visible beside the approval', () => {
    render(<RunTrace projection={projection} approvalError="审批已过期或 revision 冲突" onApprove={vi.fn()} />);
    expect(screen.getByRole('alert').textContent).toContain('revision 冲突');
    expect(screen.getByText('run.waiting_approval')).toBeTruthy();
  });
});
