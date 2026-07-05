/**
 * Backend API contract types — generated from docs/api-contract/api-contract.md (v0.1).
 *
 * These mirror the FastAPI / Pydantic schemas EXACTLY: snake_case fields and
 * the contract's literal enum values (e.g. `requires_confirmation`, not the
 * UI's `confirm`). Keep them decoupled from the UI types in `./index.ts`;
 * map between the two at the feature boundary, never edit these to fit the UI.
 */

/* ============================================================
   1. Core enums & shared types
   ============================================================ */

/** 1.1 路由四分类 (+ skill: 命中技能包路由) */
export type IntentType = 'planning' | 'scheduling' | 'query' | 'uncertain' | 'skill';

/** Engines that own a Context Panel (uncertain has none). */
export type EngineType = 'planning' | 'scheduling' | 'query';

/** 1.2 动作授权级别 */
export type AuthorizationLevel = 'auto' | 'requires_confirmation';

/** 1.3 路由由哪一层产生（四层路由） */
export type RouteSource = 'command' | 'embedding' | 'llm' | 'clarified';

/** Structured error body (the contract's `error` envelope). */
export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

/** A sub-task in a composite (cross-engine) route. */
export interface RouteStep {
  engine: IntentType;
  task: string;
}

/** 1.4 RouteDecision — consumed directly by the Route Badge. */
export interface RouteDecision {
  intent: IntentType;
  /** 0–1 */
  confidence: number;
  source: RouteSource;
  /** Extracted entities; free-form key/value. */
  entities: Record<string, unknown>;
  reason: string;
  /** 命中技能路由时的技能 ID (intent = skill 时填)。 */
  skill_id?: string | null;
  is_composite: boolean;
  /** Sub-task sequence for composite tasks, otherwise empty. */
  steps: RouteStep[];
}

/* ============================================================
   2. Orchestrator — unified chat entry
   ============================================================ */

export interface ChatStreamRequest {
  session_id: string;
  message: string;
  /** Session stickiness: the engine the conversation is currently in. */
  current_engine: EngineType | null;
  /** 技能包选择: 透传到 orchestrator；仅声明，不影响路由。 */
  skill_id?: string | null;
}

/** Clarification option offered when intent = uncertain. */
export interface ClarifyOptionApi {
  id: string;
  label: string;
  route_to: IntentType;
}

export interface ClarifyPayload {
  question: string;
  options: ClarifyOptionApi[];
}

/** 2.2 澄清回选 — answer routes directly, skipping classification. */
export interface ClarifyRequest {
  session_id: string;
  option_id: string;
  route_to: IntentType;
}

/** `context` SSE event: activate/update the right Context Panel.
 *  Payload shape depends on the engine; planning carries a SolveRun. */
export type ChatContextEvent =
  | { engine: 'planning'; payload: SolveRun }
  | { engine: 'scheduling'; payload: Record<string, unknown> }
  | { engine: 'query'; payload: Record<string, unknown> };

/** A write action held by the ActionGate awaiting human confirmation. */
export interface PendingActionPayload {
  action_id: string;
  action_type: string;
  description: string;
  params: Record<string, unknown>;
  status: 'pending' | 'executed' | 'rejected' | 'failed';
}

/** 2.3 确认/拒绝待执行动作 — `POST /chat/confirm`. */
export interface ConfirmActionRequest {
  session_id: string;
  action_id: string;
  approved: boolean;
}

/** `POST /chat/confirm` response (non-streaming ChatResponse subset). */
export interface ConfirmActionResponse {
  reply: string;
  pending_actions: PendingActionPayload[];
}

/** Discriminated union of every SSE event on `POST /chat/stream`. */
export type ChatStreamEvent =
  | { event: 'route'; data: RouteDecision }
  | { event: 'token'; data: { delta: string } }
  | { event: 'clarify'; data: ClarifyPayload }
  | { event: 'context'; data: ChatContextEvent }
  | { event: 'progress'; data: { text: string } }
  | { event: 'actions'; data: { actions: PendingActionPayload[] } }
  | { event: 'done'; data: { message_id: string } }
  | { event: 'error'; data: ApiErrorResponse };

/* ============================================================
   3. Planning engine — SolveRun is the stateful core
   ============================================================ */

export interface PlanningObjective {
  id: string;
  label: string;
  selected: boolean;
  priority: number;
}

export interface PlanningParams {
  order_scope: string[];
  lines: string[];
  due_constraints: Record<string, unknown>;
  objectives: PlanningObjective[];
}

export interface SolveRequest {
  session_id: string;
  params: PlanningParams;
}

export type SolveStatus = 'feasible' | 'infeasible' | 'timeout';

export interface SolveKpis {
  due_rate: number;
  makespan_hours: number;
  changeover_count: number;
}

export type GanttTaskType = 'production' | 'changeover' | 'downtime' | 'shortage';

export interface GanttResource {
  id: string;
  name: string;
}

export interface GanttTask {
  id: string;
  resource_id: string;
  order_id: string;
  /** ISO datetime */
  start: string;
  /** ISO datetime */
  end: string;
  type: GanttTaskType;
  label: string;
}

export interface GanttData {
  resources: GanttResource[];
  tasks: GanttTask[];
}

export interface InfeasibleConflict {
  constraint: string;
  human_readable: string;
}

export interface RelaxSuggestion {
  id: string;
  label: string;
  /** Payload to replay this relaxation. */
  action: Record<string, unknown>;
}

export interface InfeasibleReport {
  conflicts: InfeasibleConflict[];
  relax_suggestions: RelaxSuggestion[];
}

export interface SolveRun {
  solve_run_id: string;
  status: SolveStatus;
  kpis: SolveKpis;
  gantt: GanttData;
  /** Rule baseline gantt for comparison (optional). */
  baseline_gantt?: GanttData | null;
  explanation: string;
  /** Present only when status = infeasible (IIS diagnosis). */
  infeasible_report?: InfeasibleReport | null;
}

export type SolveRunList = SolveRun[];

/* ============================================================
   4. Scheduling engine
   ============================================================ */

export type KittingStatus = 'ready' | 'partial' | 'blocked';

export interface KittingMissing {
  material: string;
  qty_short: number;
}

export interface KittingItem {
  work_order: string;
  /** 物料齐套率 */
  material_rate: number;
  /** 工装齐套率 */
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
  /** Payload echoed back when executing this action. */
  action: Record<string, unknown>;
}

export interface DispatchOrdersResponse {
  orders: DispatchOrder[];
}

export interface ExecuteActionRequest {
  session_id: string;
  action_id: string;
  /** requires_confirmation actions must pass true to execute. */
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

/* ============================================================
   5. Query engine (RAG + LLM)
   ============================================================ */

export interface QueryStreamRequest {
  session_id: string;
  question: string;
}

export interface RagSource {
  id: string;
  doc_name: string;
  section: string;
  /** Retrieved snippet. */
  snippet: string;
  /** 0–1 relevance */
  relevance: number;
}

/** SSE events on `POST /query/stream`: token text, then sources before close. */
export type QueryStreamEvent =
  | { event: 'token'; data: { delta: string } }
  | { event: 'sources'; data: { sources: RagSource[] } }
  | { event: 'done'; data: { message_id: string } }
  | { event: 'error'; data: ApiErrorResponse };

/* ------------------------------------------------------------
   5.2 Knowledge base documents (RAG CRUD)
   ------------------------------------------------------------ */

/** `failed` = embedding not configured, so the doc isn't retrievable. */
export type KnowledgeDocStatus = 'ready' | 'failed';

/** One document in the RAG knowledge base. */
export interface KnowledgeDoc {
  doc_id: string;
  name: string;
  /** File extension without the dot: md / pdf / docx … */
  type: string;
  /** Number of embedded chunks currently in the vector store. */
  chunk_count: number;
  bytes: number;
  status: KnowledgeDocStatus;
  /** ISO datetime */
  added_at: string;
}

/** `GET /knowledge` response. */
export interface KnowledgeListResponse {
  docs: KnowledgeDoc[];
  /** Accepted upload extensions (with dot), for client-side validation. */
  supported_extensions: string[];
}

/** `DELETE /knowledge/{doc_id}` response. */
export interface KnowledgeDeleteResponse {
  doc_id: string;
  removed_chunks: number;
}

/* ============================================================
   6. Observability — decision log
   ============================================================ */

export type AuditEventType = 'route' | 'engine_action' | 'tool_call' | 'llm_call';

export interface AuditEvent {
  /** ISO datetime */
  ts: string;
  type: AuditEventType;
  summary: string;
  detail: Record<string, unknown>;
}

export interface AuditTimelineResponse {
  events: AuditEvent[];
}

/* ============================================================
   7. Skills — 技能包注册表 (跨引擎，不拥有 Context Panel)
   ============================================================ */

/**
 * 技能包元数据 — 镜像后端 `SkillMeta`(继承 SkillFrontmatter)。
 * 字段对齐 `scheduling_platform/skills/schemas.py`。
 */
export interface SkillMeta {
  name: string;
  display_name?: string;
  description: string;
  when_to_use?: string[];
  allowed_tools?: string[];
  user_invocable?: boolean;
  disable_model_invocation?: boolean;
  tool_preconditions?: Record<string, string[]>;
  version?: string;
  author?: string;
  file_count: number;
  bytes: number;
  /** ISO datetime */
  added_at: string;
}

/** `GET /skills` response. */
export interface SkillListResponse {
  skills: SkillMeta[];
}
