import { describe, expect, it } from 'vitest';
import { extOf, formatBytes } from './shared';

describe('formatBytes', () => {
  it('formats B / KB / MB', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB');
  });
});

describe('extOf', () => {
  it('extracts lowercase extension with dot', () => {
    expect(extOf('规则手册.PDF')).toBe('.pdf');
    expect(extOf('no-ext')).toBe('');
  });
});
