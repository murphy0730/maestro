import { createBrowserRouter, createHashRouter } from 'react-router-dom';
import { Workspace } from '@/pages/Workspace';

/**
 * `/` is the sole Runtime workspace.
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
]);
