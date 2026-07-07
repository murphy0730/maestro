import { afterEach, describe, expect, it } from 'vitest';
import { useDefaultEngineStore } from './defaultEngineStore';

afterEach(() => localStorage.clear());

describe('defaultEngineStore', () => {
  it('缺省为 auto', () => {
    expect(useDefaultEngineStore.getState().defaultEngine).toBe('auto');
  });

  it('setDefaultEngine 写入 localStorage 并更新 state', () => {
    useDefaultEngineStore.getState().setDefaultEngine('scheduling');
    expect(useDefaultEngineStore.getState().defaultEngine).toBe('scheduling');
    expect(localStorage.getItem('maestro-default-engine')).toBe('scheduling');
  });
});
