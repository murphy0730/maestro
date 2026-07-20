import { describe, expect, it } from 'vitest';
import { INITIAL_RUN_STATE, reduceRunEvents } from './runStore';

describe('run event reducer', () => {
  it('projects a fast run that upgrades without losing prior steps', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'unselected', status: 'created', steps: {}, pending_approvals: [], revision: 0 } },
      { type: 'run.path_selected', data: { path: 'fast' } },
      { type: 'step.succeeded', data: { step_id: 'read' } },
      { type: 'run.path_upgraded', data: { from: 'fast', to: 'structured', reason: 'high_risk_write' } },
    ]);
    expect(state.run?.path).toBe('structured');
    expect(state.run?.steps.read.status).toBe('succeeded');
    expect(state.upgradeReason).toBe('high_risk_write');
  });
});
