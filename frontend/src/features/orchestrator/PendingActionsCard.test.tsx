import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

afterEach(cleanup);
import type { PendingActionPayload } from '@/types';
import { PendingActionsCard } from './PendingActionsCard';

const action: PendingActionPayload = {
  action_id: 'a1',
  action_type: 'dispatch_work_order',
  description: '下发任务令 WO-104',
  params: {},
  status: 'pending',
};

it('renders a pending action and lifts confirm / reject', () => {
  const onConfirm = vi.fn();
  render(<PendingActionsCard actions={[action]} onConfirm={onConfirm} />);
  expect(screen.getByText('下发任务令 WO-104')).toBeTruthy();
  fireEvent.click(screen.getByText('确认执行'));
  expect(onConfirm).toHaveBeenCalledWith('a1', true);
  fireEvent.click(screen.getByText('拒绝'));
  expect(onConfirm).toHaveBeenCalledWith('a1', false);
});

it('renders the resolved status line instead of buttons', () => {
  render(<PendingActionsCard actions={[{ ...action, status: 'executed' }]} onConfirm={() => {}} />);
  expect(screen.getByText('已确认执行')).toBeTruthy();
  expect(screen.queryByText('确认执行')).toBeNull();
});

it('shows an executing state (spinner + label) while the action runs', () => {
  render(
    <PendingActionsCard actions={[{ ...action, status: 'executing' }]} onConfirm={() => {}} />,
  );
  expect(screen.getByText('正在执行工具…')).toBeTruthy();
  expect(screen.queryByText('确认执行')).toBeNull();
  expect(screen.queryByText('已确认执行')).toBeNull();
});

it('shows only the first open action when multiple are pending (sequential confirm)', () => {
  const second: PendingActionPayload = { ...action, action_id: 'a2', description: '第二个动作' };
  render(<PendingActionsCard actions={[action, second]} onConfirm={() => {}} />);
  expect(screen.getByText('下发任务令 WO-104')).toBeTruthy();
  expect(screen.queryByText('第二个动作')).toBeNull();
});

it('reveals the next pending action after the first resolves', () => {
  const second: PendingActionPayload = { ...action, action_id: 'a2', description: '第二个动作' };
  render(
    <PendingActionsCard actions={[{ ...action, status: 'executed' }, second]} onConfirm={() => {}} />,
  );
  expect(screen.getByText('已确认执行')).toBeTruthy();
  expect(screen.getByText('第二个动作')).toBeTruthy();
});
