import { Clock, Bell, PanelLeftOpen } from 'lucide-react';
import type { ActiveEngine } from '@/types';
import { ROUTE_META } from '@/lib/routes';
import { Badge } from '@/components/ui/Badge';

/**
 * TopBar — session title + an engine indicator that follows the active route.
 * Pure presentational; clock is passed in so the bar stays stateless. When the
 * sidebar is collapsed, shows a leading button to expand it again.
 */
interface TopBarProps {
  session: string;
  engine: ActiveEngine;
  clock: string;
  mesConnected?: boolean;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

export function TopBar({
  session,
  engine,
  clock,
  mesConnected = true,
  sidebarCollapsed = false,
  onToggleSidebar,
}: TopBarProps) {
  const m = engine ? ROUTE_META[engine] : null;
  return (
    <header className="material-chrome flex h-header flex-none items-center gap-[14px] border-b border-border-subtle px-4">
      {sidebarCollapsed && onToggleSidebar && (
        <button
          title="展开侧栏"
          onClick={onToggleSidebar}
          className="grid h-[30px] w-[30px] flex-none place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary"
        >
          <PanelLeftOpen size={16} />
        </button>
      )}
      <span className="max-w-[280px] overflow-hidden text-ellipsis whitespace-nowrap text-body-sm font-semibold text-text-primary">
        {session}
      </span>

      {m && (
        <div
          className={`inline-flex h-7 items-center gap-2 rounded-pill border py-0 pl-[9px] pr-[11px] ${m.tintBg} ${m.border}`}
        >
          <span className={`h-2 w-2 rounded-full ${m.dot} ${m.glow}`} />
          <span className={`text-caption font-semibold ${m.fg}`}>{m.zh}引擎</span>
          <span className="font-mono text-[11px] text-text-tertiary">运行中</span>
        </div>
      )}

      <span className="flex-1" />

      {mesConnected && (
        <Badge tone="success" dot size="sm">
          MES 已连接
        </Badge>
      )}
      <span className="flex items-center gap-[6px] font-mono text-caption text-text-tertiary">
        <Clock size={13} />
        {clock}
      </span>
      <span className="h-[22px] w-px bg-border-default" />
      <button
        title="通知"
        className="grid h-[30px] w-[30px] place-items-center rounded-sm text-text-tertiary transition-colors duration-fast ease-out hover:bg-border-subtle hover:text-text-secondary"
      >
        <Bell size={16} />
      </button>
    </header>
  );
}
