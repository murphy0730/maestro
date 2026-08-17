import { describe, expect, it } from 'vitest';
import { INITIAL_RUN_STATE, reduceRunEvents, useRunStore } from './runStore';

describe('run event reducer', () => {
  it('projects a fast run that upgrades without losing prior steps', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'unselected',
          status: 'created',
          steps: {},
          pending_approvals: [],
          revision: 0,
        },
      },
      { type: 'run.path_selected', data: { path: 'fast' } },
      { type: 'step.succeeded', data: { step_id: 'read' } },
      {
        type: 'run.path_upgraded',
        data: { from: 'fast', to: 'structured', reason: 'high_risk_write' },
      },
    ]);
    expect(state.run?.path).toBe('structured');
    expect(state.run?.steps.read.status).toBe('succeeded');
    expect(state.upgradeReason).toBe('high_risk_write');
  });

  it('treats run.cancelling as a supported lifecycle event', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'fast',
          status: 'running_fast',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      { type: 'run.cancelling', data: {} },
    ]);

    expect(state.run?.status).toBe('cancelling');
    expect(state.diagnostics).toEqual([]);
    expect(state.events).toContain('run.cancelling');
  });

  it('projects waiting-external and exposes meaningful events without token noise', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'structured',
          status: 'running_structured',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      { type: 'token.delta', data: { delta: 'A' } },
      { type: 'artifact.created', data: { artifact_id: 'a1' } },
      { type: 'run.waiting_external', data: {} },
    ]);
    expect(state.run?.status).toBe('waiting_external');
    expect(state.events).toEqual([
      'run.created · structured',
      'artifact.created',
      'run.waiting_external',
    ]);
  });

  it('surfaces context shedding instead of logging it as an unknown event', () => {
    // The runtime demoted old tool results to stay inside its token budget.
    // Falling through to the unknown-event branch would bury a real signal
    // under noise on every trim.
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'fast',
          status: 'running_fast',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      {
        type: 'context.shed',
        data: { limit: 48000, total_tokens: 51200, items: ['tool_result[3] -> artifact:abc'] },
      },
    ]);
    expect(state.run?.status).toBe('running_fast');
    expect(state.diagnostics).toEqual(['上下文裁剪 · 51200/48000 tokens']);
    expect(state.diagnostics.join()).not.toContain('Ignored unknown event');
  });

  it('keeps a backend failure reason visible as a diagnostic', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'fast',
          status: 'running_fast',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      { type: 'run.failed', data: { reason: 'capability timed out' } },
    ]);
    expect(state.run?.status).toBe('failed');
    expect(state.diagnostics).toContain('capability timed out');
  });

  it('keeps capability and outcome in durable event summaries for friendly rendering', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'structured',
          status: 'running_structured',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      {
        event_type: 'TOOL_CALL',
        payload: { call_id: 'c1', tool_id: 'mcp__planning__get_planning_overview', arguments: {} },
      },
      {
        event_type: 'TOOL_RESULT',
        payload: { tool_id: 'mcp__planning__get_planning_overview', status: 'succeeded' },
        references: { call_id: 'c1' },
      },
    ]);

    expect(state.events).toContain('TOOL_CALL · mcp__planning__get_planning_overview');
    expect(state.events).toContain(
      'TOOL_RESULT · mcp__planning__get_planning_overview · succeeded',
    );
  });

  it('merges a capability completion without a step id into the matching step', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'structured',
          status: 'running_structured',
          steps: { s1: { step_id: 's1', kind: 'dispatch_order', status: 'running' } },
          pending_approvals: [],
          revision: 1,
        },
      },
      { type: 'step.succeeded', data: { name: 'dispatch_order', status: 'succeeded' } },
    ]);

    expect(state.run?.steps.s1.status).toBe('succeeded');
    expect(Object.keys(state.run?.steps ?? {})).toEqual(['s1']);
  });

  it('merges a named completion into the only running placeholder step', () => {
    const state = reduceRunEvents(INITIAL_RUN_STATE, [
      {
        type: 'run.created',
        data: {
          run_id: 'r1',
          session_id: 's1',
          objective: 'x',
          path: 'structured',
          status: 'running_structured',
          steps: {},
          pending_approvals: [],
          revision: 1,
        },
      },
      { type: 'step.started', data: { step_id: 's1' } },
      { type: 'step.succeeded', data: { name: 'dispatch_order', status: 'succeeded' } },
    ]);

    expect(state.run?.steps.s1).toMatchObject({ kind: 'dispatch_order', status: 'succeeded' });
    expect(Object.keys(state.run?.steps ?? {})).toEqual(['s1']);
  });

  it('never downgrades a terminal run with a late non-terminal snapshot', () => {
    useRunStore.getState().setRun({
      run_id: 'r1',
      session_id: 's1',
      objective: 'done',
      path: 'structured',
      status: 'completed',
      steps: {},
      pending_approvals: [],
      revision: 5,
    });

    useRunStore.getState().mergeRun({
      run_id: 'r1',
      session_id: 's1',
      objective: 'done',
      path: 'structured',
      status: 'running_structured',
      steps: {},
      pending_approvals: [],
      revision: 6,
    });

    expect(useRunStore.getState().run?.status).toBe('completed');
    useRunStore.getState().reset();
  });
});
