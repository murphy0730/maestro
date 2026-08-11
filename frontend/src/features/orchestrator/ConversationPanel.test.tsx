import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ConversationPanel } from './ConversationPanel';
import type { RunProjection } from '@/stores/runStore';

afterEach(cleanup);

describe('ConversationPanel', () => {
  const emptyProjection: RunProjection = {
    run: null,
    tokens: '',
    recovered: false,
    diagnostics: [],
    events: [],
  };
  it('does not render a terminal run twice after server history commits its assistant message', () => {
    const projection: RunProjection = {
      tokens: '已完成摘要',
      recovered: false,
      diagnostics: [],
      events: [],
      run: {
        run_id: 'run-1',
        session_id: 'session-1',
        objective: '给出摘要',
        path: 'fast',
        status: 'completed',
        steps: {},
        pending_approvals: [],
        revision: 1,
        final_text: '已完成摘要',
      },
    };

    render(
      <ConversationPanel
        messages={[
          { role: 'assistant', content: '已完成摘要', ts: '2026-07-25T01:00:00Z', run_id: 'run-1' },
        ]}
        projection={projection}
        loading={false}
        streaming={false}
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getAllByText('已完成摘要')).toHaveLength(1);
  });

  it('renders real artifact download links from persisted message ids', () => {
    render(
      <ConversationPanel
        messages={[
          {
            role: 'user',
            content: '查看附件',
            ts: '2026-07-25T01:00:00Z',
            artifact_ids: ['artifact-123'],
          },
        ]}
        projection={emptyProjection}
        loading={false}
        streaming={false}
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    const link = screen.getByRole('link', { name: /产物 artifact-1/ }) as HTMLAnchorElement;
    expect(link.href).toContain('/artifacts/artifact-123');
    expect(link.download).toBe('');
  });

  it('only shows the streaming caret and scan line while tokens are arriving', () => {
    const projection: RunProjection = {
      tokens: '正在求解',
      recovered: false,
      diagnostics: [],
      events: [],
      run: {
        run_id: 'run-2',
        session_id: 'session-1',
        objective: '排产',
        path: 'fast',
        status: 'running_fast',
        steps: {},
        pending_approvals: [],
        revision: 1,
      },
    };
    const { container, rerender } = render(
      <ConversationPanel
        messages={[]}
        projection={projection}
        loading={false}
        streaming
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    expect(screen.getByTestId('streaming-caret')).toBeTruthy();
    expect((container.firstElementChild as HTMLElement).className).toContain('streaming-scan');
    rerender(
      <ConversationPanel
        messages={[]}
        projection={projection}
        loading={false}
        streaming={false}
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('streaming-caret')).toBeNull();
    expect((container.firstElementChild as HTMLElement).className).not.toContain('streaming-scan');
  });

  it('uses the persisted local personalization instead of a hard-coded user identity', () => {
    render(
      <ConversationPanel
        operatorName="陈工"
        messages={[{ role: 'user', content: '检查产线', ts: '2026-07-25T01:00:00Z' }]}
        projection={emptyProjection}
        loading={false}
        streaming={false}
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('陈工').textContent).toBe('陈');
  });

  it('deletes by message id, cascading only when a user message owns the reply below it', () => {
    const onDeleteMessage = vi.fn();
    render(
      <ConversationPanel
        messages={[
          { id: 'm1', role: 'user', content: '我的消息', ts: '2026-07-25T01:00:00Z' },
          { id: 'm2', role: 'assistant', content: 'AI 消息', ts: '2026-07-25T01:00:01Z' },
        ]}
        projection={emptyProjection}
        loading={false}
        streaming={false}
        onDeleteMessage={onDeleteMessage}
        onSuggestion={vi.fn()}
      />,
    );

    fireEvent.contextMenu(screen.getByText('我的消息').closest('article')!);
    fireEvent.click(screen.getByRole('menuitem', { name: '删除该轮对话' }));
    expect(onDeleteMessage).toHaveBeenCalledWith('m1', true);

    fireEvent.contextMenu(screen.getByText('AI 消息').closest('article')!);
    fireEvent.click(screen.getByRole('menuitem', { name: '删除消息' }));
    expect(onDeleteMessage).toHaveBeenCalledWith('m2', false);
  });

  it('offers no delete action for a message the server has not persisted yet', () => {
    render(
      <ConversationPanel
        messages={[{ role: 'user', content: '发送中', ts: '2026-07-25T01:00:00Z' }]}
        projection={emptyProjection}
        loading={false}
        streaming={false}
        onDeleteMessage={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );

    fireEvent.contextMenu(screen.getByText('发送中').closest('article')!);

    expect(screen.getByRole('menuitem', { name: '复制' })).toBeTruthy();
    expect(screen.queryByRole('menuitem', { name: /删除/ })).toBeNull();
  });

  it('refuses to delete a message whose run has not stopped, and allows it once it has', () => {
    // 删掉还在跑的那一轮的提问，后端照跑不误，最后落回来的是一条没有问题的回答。
    const runningProjection = (status: 'waiting_approval' | 'cancelled'): RunProjection => ({
      tokens: '',
      recovered: false,
      diagnostics: [],
      events: [],
      run: {
        run_id: 'run-1',
        session_id: 'session-1',
        objective: '写入',
        path: 'structured',
        status,
        steps: {},
        pending_approvals: [],
        revision: 3,
        final_text: null,
      },
    });
    const messages = [
      {
        id: 'm1',
        role: 'user' as const,
        content: '请写入',
        ts: '2026-07-25T01:00:00Z',
        run_id: 'run-1',
      },
    ];

    const { rerender } = render(
      <ConversationPanel
        messages={messages}
        projection={runningProjection('waiting_approval')}
        loading={false}
        streaming={false}
        onDeleteMessage={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    fireEvent.contextMenu(screen.getByText('请写入').closest('article')!);
    expect(screen.queryByRole('menuitem', { name: /删除/ })).toBeNull();
    expect(screen.getByText('运行进行中，请先停止再删除')).toBeTruthy();

    rerender(
      <ConversationPanel
        messages={messages}
        projection={runningProjection('cancelled')}
        loading={false}
        streaming={false}
        onDeleteMessage={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );
    fireEvent.contextMenu(screen.getByText('请写入').closest('article')!);
    expect(screen.getByRole('menuitem', { name: '删除消息' })).toBeTruthy();
  });

  it('does not still say approval is waiting after the decision was submitted', () => {
    const projection: RunProjection = {
      tokens: '',
      recovered: false,
      diagnostics: [],
      events: [],
      resuming: { approvalId: 'approval-1', approved: true },
      run: {
        run_id: 'run-approval',
        session_id: 'session-1',
        objective: '修改班次',
        path: 'structured',
        status: 'waiting_approval',
        steps: {},
        pending_approvals: [],
        revision: 4,
      },
    };

    render(
      <ConversationPanel
        messages={[]}
        projection={projection}
        loading={false}
        streaming={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByText('已确认 · 正在执行…')).toBeTruthy();
    expect(screen.queryByText('运行已暂停，等待你的审批。')).toBeNull();
  });

  it('lets the in-flight answer be copied but never deleted', () => {
    const projection: RunProjection = {
      tokens: '正在生成的回答',
      recovered: false,
      diagnostics: [],
      events: [],
      run: {
        run_id: 'run-live',
        session_id: 'session-1',
        objective: '给出摘要',
        path: 'fast',
        status: 'running_fast',
        steps: {},
        pending_approvals: [],
        revision: 1,
      },
    };
    render(
      <ConversationPanel
        messages={[]}
        projection={projection}
        loading={false}
        streaming
        onDeleteMessage={vi.fn()}
        onSuggestion={vi.fn()}
      />,
    );

    fireEvent.contextMenu(screen.getByText('正在生成的回答').closest('article')!);

    expect(screen.getByRole('menuitem', { name: '复制' })).toBeTruthy();
    expect(screen.queryByRole('menuitem', { name: /删除/ })).toBeNull();
  });

  it('copies the original message content from the context menu', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    render(
      <ConversationPanel
        messages={[{ role: 'assistant', content: '**AI 消息**', ts: '2026-07-25T01:00:01Z' }]}
        projection={emptyProjection}
        loading={false}
        streaming={false}
        onSuggestion={vi.fn()}
      />,
    );

    fireEvent.contextMenu(screen.getByText('AI 消息').closest('article')!);
    fireEvent.click(screen.getByRole('menuitem', { name: '复制' }));

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('**AI 消息**'));
  });
});
