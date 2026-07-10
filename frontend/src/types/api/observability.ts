export type AuditEventType = 'route' | 'engine_action' | 'tool_call' | 'llm_call';

export interface AuditEvent {
  ts: string;
  type: AuditEventType;
  summary: string;
  detail: Record<string, unknown>;
}

export interface AuditTimelineResponse {
  events: AuditEvent[];
}
