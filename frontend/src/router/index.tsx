import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DesignTokens } from '@/pages/DesignTokens';

/**
 * Placeholder router. Real engine routes (orchestrator / planning /
 * scheduling / query) will be wired in later — for now the shell only
 * serves the design-token preview so configuration can be verified.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/design-tokens" replace />,
  },
  {
    path: '/design-tokens',
    element: <DesignTokens />,
  },
]);
