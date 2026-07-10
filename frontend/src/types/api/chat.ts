import type { SolveRun } from './planning';
import type { SchedulingTraceStep } from './scheduling';
import type { ApiErrorResponse, EngineType, IntentType, RouteDecision } from './shared';

export type ComposerMode = 'plan' | 'auto';

export interface ChatStreamRequest {
  session_id: string;
  message: string;
  current_engine: EngineType | null;
  skill_id?: string | null;
  skill_ids?: string[];
  mode?: ComposerMode;
}

export interface ClarifyOptionApi {
  id: string;
  label: string;
  route_to: IntentType;
}

export interface ClarifyPayload {
  question: string;
  options: ClarifyOptionApi[];
}

export interface ClarifyRequest {
  session_id: string;
  option_id: string;
  route_to: IntentType;
  mode?: ComposerMode;
}

export type ChatContextEvent =
  | { engine: 'planning'; payload: SolveRun }
  | { engine: 'scheduling'; payload: { steps?: SchedulingTraceStep[]; stop_reason?: string } }
  | { engine: 'query'; payload: Record<string, unknown> };

export interface PendingActionPayload {
  action_id: string;
  action_type: string;
  description: string;
  params: Record<string, unknown>;
  status: 'pending' | 'executed' | 'rejected' | 'failed';
}

export interface ConfirmActionRequest {
  session_id: string;
  action_id: string;
  approved: boolean;
}

export interface ConfirmActionResponse {
  reply: string;
  pending_actions: PendingActionPayload[];
}

export type ChatStreamEvent =
  | { event: 'route'; data: RouteDecision }
  | { event: 'token'; data: { delta: string } }
  | { event: 'clarify'; data: ClarifyPayload }
  | { event: 'context'; data: ChatContextEvent }
  | { event: 'progress'; data: { text: string } }
  | { event: 'actions'; data: { actions: PendingActionPayload[] } }
  | { event: 'done'; data: { message_id: string } }
  | { event: 'error'; data: ApiErrorResponse };
