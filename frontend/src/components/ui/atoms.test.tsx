import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { Avatar } from './Avatar';
import { Badge } from './Badge';
import { StatusDot } from './StatusDot';

afterEach(cleanup);

describe('设计系统原子', () => {
  it('Badge 按语义色相渲染，且文本本身传达状态', () => {
    render(<Badge tone="controlled">受控执行</Badge>);
    const badge = screen.getByText('受控执行');
    expect(badge.className).toContain('text-path-controlled');
    expect(badge.className).toContain('font-mono');
  });

  it('StatusDot 只在活跃状态脉冲，且对辅助技术隐藏', () => {
    const { container, rerender } = render(<StatusDot tone="accent" pulse />);
    const dot = container.firstElementChild as HTMLElement;
    expect(dot.getAttribute('aria-hidden')).toBe('true');
    expect(dot.className).toContain('dot-pulse');
    rerender(<StatusDot tone="accent" />);
    expect((container.firstElementChild as HTMLElement).className).not.toContain('dot-pulse');
  });

  it('Avatar 用真实姓名首字与可访问名', () => {
    render(<Avatar name="周文涛" />);
    const avatar = screen.getByLabelText('周文涛');
    expect(avatar.textContent).toBe('周');
    expect(avatar.className).toContain('avatar-gradient');
  });
});
