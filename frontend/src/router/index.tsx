import { Navigate, createBrowserRouter, createHashRouter } from 'react-router-dom';
import { Workspace } from '@/pages/Workspace';
import { ExtensionCenterLayout } from '@/features/extensions/ExtensionCenterLayout';
import { SkillsPage } from '@/features/extensions/skills/SkillsPage';
import { ConnectorsPage } from '@/features/extensions/connectors/ConnectorsPage';

/**
 * `/` is the Runtime workspace; `/settings/*` is the full-width Extensions
 * Center, which keeps the session sidebar and replaces everything right of it.
 *
 * Under Electron the app is served from `file://`, where history-based routing
 * breaks — so use a hash router there and a browser router on the web.
 */
const isElectron =
  typeof navigator !== 'undefined' && navigator.userAgent.toLowerCase().includes('electron');
const createRouter = isElectron ? createHashRouter : createBrowserRouter;

export const routes = [
  { path: '/', element: <Workspace /> },
  {
    path: '/settings',
    element: <ExtensionCenterLayout />,
    children: [
      { index: true, element: <Navigate to="/settings/skills" replace /> },
      { path: 'skills', element: <SkillsPage /> },
      { path: 'connectors', element: <ConnectorsPage /> },
    ],
  },
];

export const router = createRouter(routes);
