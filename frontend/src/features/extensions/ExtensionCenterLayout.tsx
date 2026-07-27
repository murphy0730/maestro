import { useState } from 'react';
import { Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Check, Plus, Search } from 'lucide-react';
import { SessionSidebar } from '@/components/layout/SessionSidebar';
import { isMacDesktop } from '@/lib/platform';
import { useMcpServers, useSkills } from '@/api';
import { useWorkspaceSessions } from '@/hooks/useWorkspaceSessions';
import { useSessionStore } from '@/stores/sessionStore';
import { useThemeStore } from '@/stores/themeStore';
import { useUiPreferencesStore } from '@/stores/uiPreferencesStore';
import { usePersonalizationStore } from '@/stores/personalizationStore';
import { SettingsModal } from '@/features/settings/SettingsModal';
import { ExtensionDomainTabs, type ExtensionDomain } from './ExtensionDomainTabs';
import { OverlayHostContext } from './overlayHost';

/**
 * ExtensionCenterLayout — 扩展中心外框：保留左侧会话栏，中右整块换成
 * 「Header（域 Tab + 搜索 + 主按钮）+ 子路由内容 + Drawer 层」。
 *
 * TODO(shell): 会话栏在这里与 Workspace 各渲染一次（组件本身零复制，只复制调用点）。
 * 待路由层引入 AppShell 后收敛为一处。
 */
export function ExtensionCenterLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const [overlayHost, setOverlayHost] = useState<HTMLElement | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const domain: ExtensionDomain = location.pathname.includes('/connectors')
    ? 'connectors'
    : 'skills';
  const query = params.get('q') ?? '';

  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const sidebarCollapsed = useUiPreferencesStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useUiPreferencesStore((state) => state.setSidebarCollapsed);
  const setActiveSessionId = useSessionStore((state) => state.setActiveSessionId);
  const operatorName = usePersonalizationStore(
    (state) => state.data.howToAddress.trim() || '周文涛',
  );
  const workspace = useWorkspaceSessions();
  const skillsQuery = useSkills();
  const serversQuery = useMcpServers();

  const installedCount =
    domain === 'skills'
      ? (skillsQuery.data?.skills.length ?? 0)
      : (serversQuery.data?.servers.length ?? 0);

  /** 左侧任何会话操作都意味着「回到对话」——扩展中心因此自动关闭。 */
  const backToConversation = (id: string) => {
    setActiveSessionId(id);
    navigate('/');
  };

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null || value === '') next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <OverlayHostContext.Provider value={overlayHost}>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <div className="maestro-shell flex h-full flex-col bg-bg-base">
        {isMacDesktop && (
          <div className="app-drag h-[44px] flex-none border-b border-border-subtle bg-surface-1" />
        )}
        <div className="flex min-h-0 flex-1">
          <div className="noise-overlay" aria-hidden="true" />
          <SessionSidebar
            sessions={workspace.sessions}
            activeSessionId={workspace.sessionId}
            collapsed={sidebarCollapsed}
            theme={theme}
            operatorName={operatorName}
            loading={workspace.loading}
            skillsActive
            onCollapsedChange={setSidebarCollapsed}
            onCreate={() => {
              void workspace.create().then((created) => {
                if (created) backToConversation(created.session_id);
              });
            }}
            onSelect={backToConversation}
            onRename={(id, title) => {
              void workspace.rename(id, title);
            }}
            onDelete={(id) => {
              void workspace.remove(id);
            }}
            onOpenSkills={() => navigate('/settings/skills')}
            onOpenSettings={() => setSettingsOpen(true)}
            onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          />

          <main
            aria-label="扩展中心"
            className="aurora-field relative flex min-w-0 flex-1 flex-col bg-bg-base"
          >
            <header className="flex h-[56px] flex-none items-center gap-[16px] border-b border-border-subtle px-[24px]">
              <h1 className="m-0 flex-none text-[15px] font-semibold text-text-primary">
                扩展中心
              </h1>
              {/* 换域即换搜索语境，沿用旧关键词只会让人以为「什么都没有」。 */}
              <ExtensionDomainTabs domain={domain} onChange={(next) => navigate(`/settings/${next}`)} />
              <span className="flex-1" />
              <label className="glow-ring flex w-[240px] items-center gap-[8px] rounded-md border border-border-subtle bg-surface-2 px-[12px] py-[7px] text-text-tertiary transition-colors duration-fast max-lg:w-[160px]">
                <Search size={13} className="flex-none" />
                <input
                  value={query}
                  onChange={(event) => setParam('q', event.target.value)}
                  placeholder={domain === 'skills' ? '搜索技能' : '搜索连接器'}
                  aria-label={domain === 'skills' ? '搜索技能' : '搜索连接器'}
                  className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text-primary outline-none placeholder:text-text-tertiary"
                />
              </label>
              <span className="flex flex-none items-center gap-[6px] rounded-md border border-border-subtle bg-surface-2 px-[12px] py-[7px] text-[12px] text-text-secondary max-md:hidden">
                <Check size={12} />
                {domain === 'skills' ? '已安装' : '已配置'}
                <b className="font-mono text-[11px] font-medium text-text-primary">
                  {installedCount}
                </b>
              </span>
              <button
                type="button"
                onClick={() => setParam(domain === 'skills' ? 'import' : 'new', '1')}
                className="inline-flex flex-none items-center gap-[7px] rounded-sm bg-accent px-[14px] py-[7px] text-[12px] font-medium text-text-on-color shadow-glow-accent transition duration-fast ease-out hover:brightness-110 active:translate-y-px"
              >
                <Plus size={13} />
                {domain === 'skills' ? '导入技能' : '添加连接器'}
              </button>
            </header>

            <div className="relative z-[1] min-h-0 flex-1 overflow-y-auto px-[28px] pb-[60px] pt-[22px]">
              <div className="mx-auto max-w-[1280px]">
                <Outlet />
              </div>
            </div>

            {/* Drawer 的挂载点：零高度，抽屉靠 main 的定位上下文铺满内容区。 */}
            <div ref={setOverlayHost} className="flex-none" />
          </main>
        </div>
      </div>
    </OverlayHostContext.Provider>
  );
}
