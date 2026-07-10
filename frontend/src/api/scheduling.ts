import type {
  DispatchOrdersResponse,
  ExceptionImpactResponse,
  ExecuteActionRequest,
  ExecuteActionResponse,
  KittingResponse,
  ObservationPage,
} from '@/types';
import { apiGet, apiPost, withQuery } from './client';

/** `GET /observations/{ref}` — lazy-load a page of an offloaded large tool observation (方案2). */
export function getObservation(
  ref: string,
  offset = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<ObservationPage> {
  return apiGet<ObservationPage>(
    withQuery(`/observations/${encodeURIComponent(ref)}`, { offset, limit }),
    { signal },
  );
}

/** `GET /scheduling/kitting` — kitting (齐套) check for a scope. */
export function getKitting(
  sessionId: string,
  scope?: string,
  signal?: AbortSignal,
): Promise<KittingResponse> {
  return apiGet<KittingResponse>(
    withQuery('/scheduling/kitting', { session_id: sessionId, scope }),
    { signal },
  );
}

/** `GET /scheduling/dispatch-orders` — pending dispatch orders (task 任务令). */
export function getDispatchOrders(
  sessionId: string,
  signal?: AbortSignal,
): Promise<DispatchOrdersResponse> {
  return apiGet<DispatchOrdersResponse>(
    withQuery('/scheduling/dispatch-orders', { session_id: sessionId }),
    { signal },
  );
}

/** `POST /scheduling/execute` — execute a dispatch action (with confirmation). */
export function executeAction(
  req: ExecuteActionRequest,
  signal?: AbortSignal,
): Promise<ExecuteActionResponse> {
  return apiPost<ExecuteActionResponse>('/scheduling/execute', req, { signal });
}

/** `GET /scheduling/exception-impact` — blast radius of an exception event. */
export function getExceptionImpact(
  sessionId: string,
  eventId: string,
  signal?: AbortSignal,
): Promise<ExceptionImpactResponse> {
  return apiGet<ExceptionImpactResponse>(
    withQuery('/scheduling/exception-impact', { session_id: sessionId, event_id: eventId }),
    { signal },
  );
}
