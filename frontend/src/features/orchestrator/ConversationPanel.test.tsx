import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ConversationPanel } from './ConversationPanel';
import type { RunProjection } from '@/stores/runStore';

afterEach(cleanup);

describe('ConversationPanel', () => {
  const emptyProjection: RunProjection = { run: null, tokens: '', recovered: false, diagnostics: [], events: [] };
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
        messages={[{ role: 'assistant', content: '已完成摘要', ts: '2026-07-25T01:00:00Z', run_id: 'run-1' }]}
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
    render(<ConversationPanel messages={[{ role: 'user', content: '查看附件', ts: '2026-07-25T01:00:00Z', artifact_ids: ['artifact-123'] }]} projection={emptyProjection} loading={false} streaming={false} onRetry={vi.fn()} onSuggestion={vi.fn()} />);
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
      run: { run_id: 'run-2', session_id: 'session-1', objective: '排产', path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 1 },
    };
    const { container, rerender } = render(<ConversationPanel messages={[]} projection={projection} loading={false} streaming onRetry={vi.fn()} onSuggestion={vi.fn()} />);
    expect(screen.getByTestId('streaming-caret')).toBeTruthy();
    expect((container.firstElementChild as HTMLElement).className).toContain('streaming-scan');
    rerender(<ConversationPanel messages={[]} projection={projection} loading={false} streaming={false} onRetry={vi.fn()} onSuggestion={vi.fn()} />);
    expect(screen.queryByTestId('streaming-caret')).toBeNull();
    expect((container.firstElementChild as HTMLElement).className).not.toContain('streaming-scan');
  });

  it('uses the persisted local personalization instead of a hard-coded user identity', () => {
    render(<ConversationPanel operatorName="陈工" messages={[{ role: 'user', content: '检查产线', ts: '2026-07-25T01:00:00Z' }]} projection={emptyProjection} loading={false} streaming={false} onRetry={vi.fn()} onSuggestion={vi.fn()} />);
    expect(screen.getByLabelText('陈工').textContent).toBe('陈');
  });
});
