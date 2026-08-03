import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunTrace } from './RunTrace';
import { describeCapability } from './capabilityLabel';
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
  it('shows controlled execution and disables approval while in flight', () => {
    render(<RunTrace projection={projection} approvingId="a1" onApprove={vi.fn()} />);
    expect(screen.getByText('已升级为受控执行')).toBeTruthy();
    expect(screen.getByText('等待确认')).toBeTruthy();
    expect((screen.getByRole('button', { name: '确认' }) as HTMLButtonElement).disabled).toBe(true);
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
          s1: { step_id: 's1', kind: '拉取工单', status: 'succeeded' as const },
          s2: { step_id: 's2', kind: '生成方案', status: 'running' as const },
        },
      },
    };
    const { container } = render(<RunTrace projection={withSteps} onApprove={vi.fn()} />);
    expect(screen.getByText('步骤 · 1/2')).toBeTruthy();
    // 认不出的能力名原样透出，不因为翻译不了就藏起来。s1 同时是待审批的目标，
    // 所以它在步骤行和审批卡片各出现一次。
    expect(screen.getAllByText('拉取工单')).toHaveLength(2);
    expect(screen.getByText('生成方案')).toBeTruthy();
    // 状态同时用文字表达，不只靠颜色。
    expect(screen.getByText('成功')).toBeTruthy();
    expect(screen.getByText('运行中')).toBeTruthy();
    expect(container.querySelectorAll('.step-timeline > li')).toHaveLength(2);
  });

  it('names a capability instead of its registry id, keeping the raw name one click away', () => {
    const withSteps = {
      ...projection,
      run: {
        ...projection.run,
        pending_approvals: [],
        steps: {
          s2: {
            step_id: 's2',
            kind: 'mcp__jira__create_issue',
            status: 'succeeded' as const,
            call: { name: 'mcp__jira__create_issue', arguments: { summary: '缺料' } },
          },
        },
      },
    };
    const describe = (name: string) =>
      describeCapability(name, {
        servers: [
          {
            name: 'jira',
            command: 'jira-mcp',
            args: [],
            env_keys: [],
            enabled: true,
            read_only_tools: [],
            status: 'connected' as const,
            error: '',
            tools: [
              {
                name: 'create_issue',
                capability: 'mcp__jira__create_issue',
                description: '创建议题。会写入 Jira。',
                read_only: false,
                writes: true,
                risk: 'high' as const,
              },
            ],
          },
        ],
      });

    render(<RunTrace projection={withSteps} onApprove={vi.fn()} describe={describe} />);
    expect(screen.getByText('创建议题')).toBeTruthy();
    expect(screen.getByText('jira · 连接器')).toBeTruthy();
    expect(screen.getByText('MCP')).toBeTruthy();
    // 写操作要有文字，不能只靠颜色。
    expect(screen.getByText('写操作')).toBeTruthy();
    // 原始注册名与参数默认收起 —— 翻译是为了可读，不是为了藏。
    expect(screen.queryByText('mcp__jira__create_issue')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '展开创建议题的调用详情' }));
    expect(screen.getByText('mcp__jira__create_issue')).toBeTruthy();
    expect(screen.getByText(/"summary": "缺料"/)).toBeTruthy();
  });

  it('translates the built-in host primitives without any directory', () => {
    const withSteps = {
      ...projection,
      run: {
        ...projection.run,
        pending_approvals: [],
        steps: { s2: { step_id: 's2', kind: 'read_file', status: 'succeeded' as const } },
      },
    };
    render(<RunTrace projection={withSteps} onApprove={vi.fn()} />);
    expect(screen.getByText('读取文件')).toBeTruthy();
    expect(screen.getByText('本机工具')).toBeTruthy();
  });

  it('spells out the error kind beside the message', () => {
    const withSteps = {
      ...projection,
      run: {
        ...projection.run,
        pending_approvals: [],
        steps: {
          s2: {
            step_id: 's2',
            kind: 'write_file',
            status: 'failed' as const,
            error_kind: 'schema_input',
            error_message: 'path 超出工作区',
          },
        },
      },
    };
    render(<RunTrace projection={withSteps} onApprove={vi.fn()} />);
    expect(screen.getByText(/参数不合法 · path 超出工作区/)).toBeTruthy();
  });

  it('says which capability an approval is actually for', () => {
    const withStep = {
      ...projection,
      run: {
        ...projection.run,
        steps: {
          s1: {
            step_id: 's1',
            kind: 'bash',
            status: 'waiting_approval' as const,
            call: { name: 'bash', arguments: { command: 'rm -rf build' } },
          },
        },
      },
    };
    const { container } = render(<RunTrace projection={withStep} onApprove={vi.fn()} />);
    // 卡片原本只有一句 impact_summary，看不出在批哪个能力。
    const card = within(container.querySelector('.approval-card') as HTMLElement);
    expect(card.getByText('执行命令')).toBeTruthy();
    expect(card.getByText('写入 MES')).toBeTruthy();
    fireEvent.click(card.getByRole('button', { name: '展开调用参数' }));
    expect(card.getByText(/"command": "rm -rf build"/)).toBeTruthy();
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
    expect(screen.getByText('运行轨迹 · 全屏')).toBeTruthy();
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
    expect(screen.getByText('run.waiting_approval')).toBeTruthy();
  });
});
