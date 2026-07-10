import type { AuthorizationLevel } from './shared';

export interface SchedulingTraceStep {
  thought?: string;
  tool: string;
  arguments?: Record<string, unknown>;
  observation?: { observation_ref?: string; total?: number; hint?: string } & Record<
    string,
    unknown
  >;
  blocked?: boolean;
}

export interface ObservationPage {
  observation_ref: string;
  kind: 'list' | 'dict' | 'scalar';
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  items?: unknown[];
  keys?: Record<string, unknown>;
  slice?: string;
  item_keys?: string[];
  preview?: unknown;
}

export type KittingStatus = 'ready' | 'partial' | 'blocked';

export interface KittingMissing {
  material: string;
  qty_short: number;
}

export interface KittingItem {
  work_order: string;
  material_rate: number;
  tooling_rate: number;
  status: KittingStatus;
  missing: KittingMissing[];
}

export interface KittingResponse {
  items: KittingItem[];
}

export interface DispatchOrder {
  id: string;
  line: string;
  summary: string;
  authorization: AuthorizationLevel;
  action: Record<string, unknown>;
}

export interface DispatchOrdersResponse {
  orders: DispatchOrder[];
}

export interface ExecuteActionRequest {
  session_id: string;
  action_id: string;
  confirmed: boolean;
}

export type ExecuteStatus = 'executed' | 'rejected' | 'pending';

export interface ExecuteActionResponse {
  status: ExecuteStatus;
  audit_id: string;
  message: string;
}

export interface SuggestedAction {
  label: string;
  authorization: AuthorizationLevel;
  action: Record<string, unknown>;
}

export interface ExceptionImpactResponse {
  trigger: string;
  affected_orders: string[];
  suggested_actions: SuggestedAction[];
}
