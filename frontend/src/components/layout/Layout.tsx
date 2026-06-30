import type { ReactNode } from 'react';

/**
 * Layout — the app frame: a fixed left sidebar beside a body of a top bar over
 * two columns (conversation on the left, context panel on the right). The right
 * column collapses when no panel is supplied. Pure presentational shell.
 */
interface LayoutProps {
  sidebar: ReactNode;
  topBar: ReactNode;
  conversation: ReactNode;
  panel?: ReactNode;
}

export function Layout({ sidebar, topBar, conversation, panel }: LayoutProps) {
  return (
    <div className="flex h-full bg-bg-base">
      {sidebar}
      <div className="flex min-w-0 flex-1 flex-col">
        {topBar}
        <div className="flex min-h-0 flex-1">
          <main className={`flex min-w-0 flex-1 flex-col ${panel ? 'border-r border-border-subtle' : ''}`}>
            {conversation}
          </main>
          {panel && <div className="flex w-[42%] min-w-[388px] max-w-[600px] flex-none">{panel}</div>}
        </div>
      </div>
    </div>
  );
}
