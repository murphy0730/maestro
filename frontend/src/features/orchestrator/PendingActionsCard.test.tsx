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
