import { describe, expect, it } from 'vitest';
import { storedToThread } from './history';
import type { StoredMessage } from '@/api/sessions';

const msg = (over: Partial<StoredMessage>): StoredMessage => ({
  role: 'assistant',
  content: 'x',
  ts: '2026-07-07T12:00:00Z',
  ...over,
});

describe('storedToThread', () => {
  it('空列表只返回欢迎系统消息', () => {
    const t = storedToThread([]);
    expect(t).toHaveLength(1);
    expect(t[0].kind).toBe('system');
  });

  it('user→user，assistant(normal)→agent，assistant(system)→system', () => {
    const t = storedToThread([
      msg({ role: 'user', content: '派工 WO-1' }),
      msg({ role: 'assistant', content: '主回答', kind: 'normal' }),
      msg({ role: 'assistant', content: '已执行: 派工 — ok', kind: 'system' }),
    ]);
    // t[0] 是欢迎系统消息
    expect(t[1].kind).toBe('user');
    expect(t[2].kind).toBe('agent');
    expect(t[3].kind).toBe('system');
    expect((t[3] as { text: string }).text).toBe('已执行: 派工 — ok');
  });

  it('缺省 kind 视为 normal→agent', () => {
    const t = storedToThread([msg({ role: 'assistant', content: '旧数据' })]);
    expect(t[1].kind).toBe('agent');
  });
});
