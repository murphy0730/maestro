import { createBrowserRouter } from 'react-router-dom';
import { Workspace } from '@/pages/Workspace';
import { DesignTokens } from '@/pages/DesignTokens';

/**
 * Routes. `/` is the main workspace (static UI, mock-driven);
 * `/design-tokens` keeps the token preview for design verification.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Workspace />,
  },
  {
    path: '/design-tokens',
    element: <DesignTokens />,
  },
]);
