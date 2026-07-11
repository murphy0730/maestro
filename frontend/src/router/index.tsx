import { lazy, Suspense } from 'react';
import { createBrowserRouter, createHashRouter } from 'react-router-dom';
import { Workspace } from '@/pages/Workspace';
import { DesignTokens } from '@/pages/DesignTokens';

const Tasks = lazy(async () => ({ default: (await import('@/pages/Tasks')).Tasks }));
const ExtensionCenterPage = lazy(async () => ({ default: (await import('@/features/extensions/ExtensionCenterPage')).ExtensionCenterPage }));

/**
 * Routes. `/` is the main workspace; `/tasks` is the task list for a planning
 * run; `/design-tokens` is the token preview.
 *
 * Under Electron the app is served from `file://`, where history-based routing
 * breaks — so use a hash router there and a browser router on the web.
 */
const isElectron =
  typeof navigator !== 'undefined' && navigator.userAgent.toLowerCase().includes('electron');
const createRouter = isElectron ? createHashRouter : createBrowserRouter;

export const router = createRouter([
  {
    path: '/settings/:section',
    element: <Suspense fallback={<div className="p-6 text-text-tertiary">加载扩展中心…</div>}><ExtensionCenterPage /></Suspense>,
  },
  {
    path: '/',
    element: <Workspace />,
  },
  {
    path: '/tasks',
    element: (
      <Suspense fallback={<div className="p-6 text-body-sm text-text-tertiary">加载任务列表…</div>}>
        <Tasks />
      </Suspense>
    ),
  },
  {
    path: '/design-tokens',
    element: <DesignTokens />,
  },
]);
