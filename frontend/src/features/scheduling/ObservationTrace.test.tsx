import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/api', () => ({ getObservation: vi.fn() }));

afterEach(cleanup);
import { getObservation } from '@/api';
import type { SchedulingTraceStep } from '@/types';
import { ObservationTrace } from './ObservationTrace';

const offloaded: SchedulingTraceStep = {
  tool: 'query_inventory',
  observation: { observation_ref: 'obs-1', total: 847 },
};

it('lazy-loads an offloaded observation on demand', async () => {
  vi.mocked(getObservation).mockResolvedValue({
    observation_ref: 'obs-1',
    kind: 'list',
    total: 847,
    items: [{ material_id: 'M-002' }],
    has_more: true,
  });
  render(<ObservationTrace steps={[offloaded]} />);

  expect(screen.getByText('query_inventory')).toBeTruthy();
  expect(screen.getByText('847 条')).toBeTruthy();
  fireEvent.click(screen.getByText('查看完整结果'));

  expect(getObservation).toHaveBeenCalledWith('obs-1');
  await waitFor(() => expect(screen.getByText(/M-002/)).toBeTruthy());
});

it('renders no load button for a small inline observation', () => {
  render(<ObservationTrace steps={[{ tool: 'check_kitting', observation: { ok: true } }]} />);
  expect(screen.queryByText('查看完整结果')).toBeNull();
});
