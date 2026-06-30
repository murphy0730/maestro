/**
 * MSW request mocking for the backend API contract. Enabled in dev unless
 * `VITE_API_MOCKING=disabled`. Call {@link enableApiMocking} before rendering.
 */
export async function enableApiMocking(): Promise<void> {
  if (!import.meta.env.DEV || import.meta.env.VITE_API_MOCKING === 'disabled') return;
  const { worker } = await import('./browser');
  await worker.start({
    onUnhandledRequest: 'bypass', // let Vite assets / HMR through untouched
  });
}

export { handlers } from './handlers';
