import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SettingsModal } from './SettingsModal';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import { useUiPreferencesStore } from '@/stores/uiPreferencesStore';

describe('SettingsModal', () => {
  afterEach(cleanup);

  it('updates real theme and reduced-motion preferences', () => {
    render(<SettingsModal open onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('主题'), { target: { value: 'light' } });
    expect(document.documentElement.dataset.theme).toBe('light');
    fireEvent.click(screen.getByRole('switch', { name: '减少动效' }));
    expect(document.documentElement.dataset.reducedMotion).toBe('true');
  });

  it('persists default mode, trace state and existing personalization fields', () => {
    render(<SettingsModal open onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('默认模式'), { target: { value: 'query' } });
    fireEvent.change(screen.getByLabelText('运行详情栏默认状态'), { target: { value: 'hidden' } });
    // 个性化是独立分区（设计稿 I 的左侧菜单），先切换再改真实字段。
    fireEvent.click(screen.getByRole('button', { name: '个性化' }));
    fireEvent.change(screen.getByLabelText('称呼'), { target: { value: '陈工' } });
    fireEvent.change(screen.getByLabelText('回复语气'), { target: { value: 'concise' } });
    expect(useUiPreferencesStore.getState()).toMatchObject({
      defaultMode: 'query',
      traceDefault: 'hidden',
    });
    expect(usePersonalizationStore.getState().data).toMatchObject({
      howToAddress: '陈工',
      tone: 'concise',
    });
    expect((screen.getByRole('button', { name: /授权与审批/ }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
