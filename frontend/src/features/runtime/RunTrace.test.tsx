import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunTrace } from './RunTrace';
const projection = { tokens: '', diagnostics: [], upgradeReason: 'write', run: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'structured' as const, status: 'waiting_approval' as const, steps: {}, final_text: null, revision: 2, pending_approvals: [{ approval_id: 'a1', step_id: 's1', impact_summary: '写入 MES', policy_reason: 'high risk', run_revision: 2, status: 'pending' as const }] } };
describe('RunTrace', () => {
  afterEach(cleanup);
  it('shows controlled execution and disables approval while in flight', () => {
    render(<RunTrace projection={projection} approvingId="a1" onApprove={vi.fn()} />);
    expect(screen.getByText('已升级为受控执行')).toBeTruthy(); expect(screen.getByText('等待确认')).toBeTruthy();
    expect((screen.getByRole('button', { name: '确认' }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('sends an approval choice', () => { const onApprove = vi.fn(); render(<RunTrace projection={projection} onApprove={onApprove} />); fireEvent.click(screen.getByRole('button', { name: '拒绝' })); expect(onApprove).toHaveBeenCalledWith(projection.run.pending_approvals[0], false); });
});
