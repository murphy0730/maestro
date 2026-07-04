import { expect, it } from 'vitest';
import { useSessionStore } from './sessionStore';

it('tracks the active session id', () => {
  expect(useSessionStore.getState().activeSessionId).toBeNull();
  useSessionStore.getState().setActiveSessionId('s1');
  expect(useSessionStore.getState().activeSessionId).toBe('s1');
  useSessionStore.getState().setActiveSessionId(null);
  expect(useSessionStore.getState().activeSessionId).toBeNull();
});
