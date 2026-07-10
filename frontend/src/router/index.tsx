import { createBrowserRouter, createHashRouter } from 'react-router-dom';
import { Workspace } from '@/pages/Workspace';
import { Tasks } from '@/pages/Tasks';
import { DesignTokens } from '@/pages/DesignTokens';

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
    path: '/',
    element: <Workspace />,
  },
  {
    path: '/tasks',
    element: <Tasks />,
  },
  {
    path: '/design-tokens',
    element: <DesignTokens />,
  },
]);
