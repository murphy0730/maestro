import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

/** MSW worker that intercepts API requests in the browser during dev. */
export const worker = setupWorker(...handlers);
