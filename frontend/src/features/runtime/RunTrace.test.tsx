import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunTrace } from './RunTrace';
const projection = {
  tokens: '',
  diagnostics: [],
  events: ['run.waiting_approval'],
  recovered: false,
  upgradeReason: 'write',
  run: {
    run_id: 'r1',
    session_id: 's1',
    objective: 'x',
    path: 'structured' as const,
    status: 'waiting_approval' as const,
    steps: {},
    final_text: null,
    revision: 2,
    pending_approvals: [
      {
        approval_id: 'a1',
        step_id: 's1',
        impact_summary: '写入 MES',
        policy_reason: 'high risk',
        run_revision: 2,
        status: 'pending' as const,
      },
    ],
  },
};
describe('RunTrace', () => {
  afterEach(cleanup);
  it('shows controlled execution while an approval is waiting', () => {
    render(<RunTrace projection={projection} onApprove={vi.fn()} />);
    expect(screen.getByText('已升级为受控执行')).toBeTruthy();
    expect(screen.getByText('等待确认')).toBeTruthy();
    expect(screen.getByRole('button', { name: '确认' })).toBeTruthy();
  });
  it('retires the approval card the moment the decision is submitted', () => {
    // 确认是人已经做完的动作；卡片继续摆在那里会让人以为没点上。
    render(
      <RunTrace
        projection={{ ...projection, resuming: { approvalId: 'a1', approved: true } }}
        onApprove={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: '确认' })).toBeNull();
    expect(screen.getByText('已确认 · 正在执行…')).toBeTruthy();
  });
  it('marks which round a multi-confirmation approval is on', () => {
    // 双重确认的第二轮与第一轮长得一样，不标出来会让人以为上次没点上。
    const withRounds = (confirmations: string[]) => ({
      ...projection,
      run: {
        ...projection.run,
        pending_approvals: [
          { ...projection.run.pending_approvals[0], confirmations, confirmations_required: 2 },
        ],
      },
    });

    const { unmount } = render(<RunTrace projection={withRounds([])} onApprove={vi.fn()} />);
    expect(screen.getByText('第 1/2 次确认')).toBeTruthy();
    unmount();

    render(<RunTrace projection={withRounds(['alice'])} onApprove={vi.fn()} />);
    expect(screen.getByText('第 2/2 次确认')).toBeTruthy();
    expect(screen.getByText(/外部状态在两次之间未发生变化/)).toBeTruthy();
  });
  it('does not clutter an ordinary single-confirmation approval', () => {
    render(<RunTrace projection={projection} onApprove={vi.fn()} />);
    expect(screen.queryByText(/次确认/)).toBeNull();
  });
  it('sends an approval choice', () => {
    const onApprove = vi.fn();
    render(<RunTrace projection={projection} onApprove={onApprove} />);
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));
    expect(onApprove).toHaveBeenCalledWith(projection.run.pending_approvals[0], false);
  });
  it('does not offer a stale approval after the run has already failed', () => {
    render(
      <RunTrace
        projection={{ ...projection, run: { ...projection.run, status: 'failed' } }}
        onApprove={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: '确认' })).toBeNull();
    expect(screen.getAllByText('执行失败').length).toBeGreaterThan(0);
  });
  it('does not call waiting external recovered', () => {
    render(
      <RunTrace
        projection={{ ...projection, run: { ...projection.run, status: 'waiting_external' } }}
        onApprove={vi.fn()}
      />,
    );
    expect(screen.getByText('等待外部完成')).toBeTruthy();
    expect(screen.queryByText('已恢复')).toBeNull();
  });
  it('offers dock, hide and fullscreen controls', () => {
    const onViewChange = vi.fn();
    render(
      <RunTrace
        projection={projection}
        onApprove={vi.fn()}
        view="docked"
        onViewChange={onViewChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '全屏运行详情' }));
    expect(onViewChange).toHaveBeenCalledWith('fullscreen');
    fireEvent.click(screen.getByRole('button', { name: '隐藏运行详情' }));
    expect(onViewChange).toHaveBeenCalledWith('hidden');
  });
  it('renders a step timeline from the real snapshot steps', () => {
    const withSteps = {
      ...projection,
      run: {
        ...projection.run,
        steps: {
          s1: {
            step_id: 's1',
            kind: 'Apply the selected skill to the objective',
            status: 'succeeded' as const,
          },
          s2: {
            step_id: 's2',
            kind: 'mcp__planning__get_planning_overview',
            status: 'running' as const,
          },
        },
      },
    };
    const { container } = render(<RunTrace projection={withSteps} onApprove={vi.fn()} />);
    expect(screen.getByText('执行步骤')).toBeTruthy();
    expect(screen.getByText('1/2 已完成')).toBeTruthy();
    expect(screen.getByText('执行任务所需能力')).toBeTruthy();
    expect(screen.getByText('获取排产方案概览')).toBeTruthy();
    expect(screen.getByText('排产服务')).toBeTruthy();
    expect(screen.queryByText('mcp__planning__get_planning_overview')).toBeNull();
    // 状态同时用文字表达，不只靠颜色。
    expect(screen.getByText('已完成')).toBeTruthy();
    expect(screen.getByText('正在执行')).toBeTruthy();
    expect(container.querySelectorAll('.step-timeline > li')).toHaveLength(2);
  });

  it('turns raw runtime events into compact operator-facing activity', () => {
    render(
      <RunTrace
        projection={{
          ...projection,
          events: [
            'RUN_CREATED',
            'CONTEXT_BUILT',
            'TOOL_CALL · mcp__planning__get_planning_overview',
            'MODEL_TURN',
            'TOOL_RESULT · mcp__planning__get_planning_overview · succeeded',
            'RUN_STATUS_CHANGED · completed · model_final',
          ],
        }}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.getByText('活动记录')).toBeTruthy();
    expect(screen.getByText('获取排产方案概览')).toBeTruthy();
    expect(screen.getByText('已完成 · 排产服务')).toBeTruthy();
    expect(screen.getByText('运行已完成')).toBeTruthy();
    expect(screen.getByText('技术事件 · 3')).toBeTruthy();
    expect(screen.queryByText('mcp__planning__get_planning_overview')).toBeNull();
    expect(screen.queryByText('RUN_STATUS_CHANGED')).toBeNull();
  });

  it('lays the fullscreen view out as steps beside the pending approval', () => {
    const { container } = render(
      <RunTrace
        projection={projection}
        onApprove={vi.fn()}
        view="fullscreen"
        onViewChange={vi.fn()}
      />,
    );
    expect(screen.getByText('运行详情 · 全屏')).toBeTruthy();
    expect(screen.getByRole('button', { name: '还原驻留详情' })).toBeTruthy();
    expect(container.querySelector('.grid-cols-\\[1\\.1fr_\\.9fr\\]')).toBeTruthy();
    expect(screen.getByText('写入 MES')).toBeTruthy();
  });

  it('keeps revision conflicts and network failures visible beside the approval', () => {
    render(
      <RunTrace
        projection={projection}
        approvalError="审批已过期或 revision 冲突"
        onApprove={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert').textContent).toContain('revision 冲突');
    expect(screen.getAllByText('等待审批').length).toBeGreaterThan(0);
    expect(screen.queryByText('run.waiting_approval')).toBeNull();
  });
});
