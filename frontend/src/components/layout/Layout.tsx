import type { ReactNode } from 'react';
import { isMacDesktop } from '@/lib/platform';

/**
 * Layout — the app frame: a fixed left sidebar beside a body of a top bar over
 * two columns (conversation on the left, context panel on the right). The right
 * column collapses when no panel is supplied. Pure presentational shell.
 *
 * On the macOS Electron shell (hiddenInset titlebar) a dedicated 44px drag
 * strip sits at the very top — the traffic lights live there, and the app
 * chrome (sidebar/topbar) starts below it instead of colliding with them.
 */
interface LayoutProps {
  sidebar?: ReactNode;
  topBar: ReactNode;
  conversation: ReactNode;
  panel?: ReactNode;
}

export function Layout({ sidebar, topBar, conversation, panel }: LayoutProps) {
  return (
    <div className="flex h-full flex-col bg-bg-base">
      {isMacDesktop && (
        <div className="app-drag material-chrome h-[44px] flex-none border-b border-border-subtle" />
      )}
      <div className="flex min-h-0 flex-1">
        {sidebar}
        <div className="flex min-w-0 flex-1 flex-col">
          {topBar}
          <div className="flex min-h-0 flex-1">
            <main
              className={`flex min-w-0 flex-1 flex-col ${panel ? 'border-r border-border-subtle' : ''}`}
            >
              {conversation}
            </main>
            {panel && (
              <div className="flex w-[42%] min-w-[388px] max-w-[600px] flex-none">{panel}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
