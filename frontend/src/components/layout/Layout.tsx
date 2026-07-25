import type { ReactNode } from 'react';
import { isMacDesktop } from '@/lib/platform';

/**
 * Layout — 设计稿 06 的应用框：左侧会话侧栏 + 中央工作区（顶栏 / 对话 / Composer）
 * + 右侧运行详情栏。详情栏由 `conversation` 自行携带，因为它的驻留/隐藏/全屏三态
 * 需要跟对话区共享同一个定位上下文。
 *
 * 极光只铺在中央工作区（设计稿 .f-main::before），蓝图网格铺满整个外框；
 * macOS Electron（hiddenInset 标题栏）顶部保留 44px 拖拽区，红绿灯不与应用 chrome 冲突。
 */
interface LayoutProps {
  sidebar?: ReactNode;
  topBar: ReactNode;
  conversation: ReactNode;
}

export function Layout({ sidebar, topBar, conversation }: LayoutProps) {
  return (
    <div className="maestro-shell flex h-full flex-col bg-bg-base">
      {isMacDesktop && (
        <div className="app-drag h-[44px] flex-none border-b border-border-subtle bg-surface-1" />
      )}
      <div className="flex min-h-0 flex-1">
        <div className="noise-overlay" aria-hidden="true" />
        {sidebar}
        <div className="aurora-field flex min-w-0 flex-1 flex-col bg-bg-base">
          {topBar}
          <div className="flex min-h-0 flex-1">{conversation}</div>
        </div>
      </div>
    </div>
  );
}
