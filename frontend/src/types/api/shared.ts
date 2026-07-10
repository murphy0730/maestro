export type IntentType = 'planning' | 'scheduling' | 'query' | 'uncertain' | 'skill';

export type EngineType = 'planning' | 'scheduling' | 'query';

export type AuthorizationLevel = 'auto' | 'requires_confirmation';

export type RouteSource = 'command' | 'embedding' | 'llm' | 'clarified';

export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

export interface RouteStep {
  engine: IntentType;
  task: string;
}

export interface RouteDecision {
  intent: IntentType;
  confidence: number;
  source: RouteSource;
  entities: Record<string, unknown>;
  reason: string;
  skill_id?: string | null;
  is_composite: boolean;
  steps: RouteStep[];
}
