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

  it('treats run.cancelling as a supported lifecycle event', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 1 } },
      { type: 'run.cancelling', data: {} },
    ]);

    expect(state.run?.status).toBe('cancelling');
    expect(state.diagnostics).toEqual([]);
    expect(state.events).toContain('run.cancelling');
  });

  it('projects waiting-external and exposes meaningful events without token noise', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'structured', status: 'running_structured', steps: {}, pending_approvals: [], revision: 1 } },
      { type: 'token.delta', data: { delta: 'A' } },
      { type: 'artifact.created', data: { artifact_id: 'a1' } },
      { type: 'run.waiting_external', data: {} },
    ]);
    expect(state.run?.status).toBe('waiting_external');
    expect(state.events).toEqual(['run.created · structured', 'artifact.created', 'run.waiting_external']);
  });

  it('keeps a backend failure reason visible as a diagnostic', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'fast', status: 'running_fast', steps: {}, pending_approvals: [], revision: 1 } },
      { type: 'run.failed', data: { reason: 'capability timed out' } },
    ]);
    expect(state.run?.status).toBe('failed');
    expect(state.diagnostics).toContain('capability timed out');
  });

  it('merges a capability completion without a step id into the matching step', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'structured', status: 'running_structured', steps: { s1: { step_id: 's1', kind: 'dispatch_order', status: 'running' } }, pending_approvals: [], revision: 1 } },
      { type: 'step.succeeded', data: { name: 'dispatch_order', status: 'succeeded' } },
    ]);

    expect(state.run?.steps.s1.status).toBe('succeeded');
    expect(Object.keys(state.run?.steps ?? {})).toEqual(['s1']);
  });

  it('merges a named completion into the only running placeholder step', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      { type: 'run.created', data: { run_id: 'r1', session_id: 's1', objective: 'x', path: 'structured', status: 'running_structured', steps: {}, pending_approvals: [], revision: 1 } },
      { type: 'step.started', data: { step_id: 's1' } },
      { type: 'step.succeeded', data: { name: 'dispatch_order', status: 'succeeded' } },
    ]);

    expect(state.run?.steps.s1).toMatchObject({ kind: 'dispatch_order', status: 'succeeded' });
    expect(Object.keys(state.run?.steps ?? {})).toEqual(['s1']);
  });
});
