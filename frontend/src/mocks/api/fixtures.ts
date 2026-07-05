/**
 * Mock API responses, shaped EXACTLY to docs/api-contract/api-contract.md (snake_case,
 * contract enums). Consumed only by the MSW handlers. The demo narrative
 * (B 线 / WO-4830 急单) matches the UI mocks for a coherent dev experience.
 */
import type {
  AuditTimelineResponse,
  ClarifyPayload,
  DispatchOrdersResponse,
  ExceptionImpactResponse,
  GanttData,
  KittingResponse,
  KnowledgeDoc,
  RagSource,
  RouteDecision,
  SkillMeta,
  SolveRun,
} from '@/types';

/* ---- Orchestrator ---- */

export const ROUTE_PLANNING: RouteDecision = {
  intent: 'planning',
  confidence: 0.92,
  source: 'llm',
  entities: { line: 'B 线', scope: '明日排产', target_delta: '+20%' },
  reason: '目标产量调整属计划层重排，需重新求解产能约束',
  is_composite: false,
  steps: [],
};

export const ROUTE_UNCERTAIN: RouteDecision = {
  intent: 'uncertain',
  confidence: 0.41,
  source: 'llm',
  entities: { work_order: 'WO-4830' },
  reason: '意图可指向多个执行动作，置信不足以自动路由',
  is_composite: false,
  steps: [],
};

export const CLARIFY_4830: ClarifyPayload = {
  question: '「先安排上 WO-4830」有两种执行方式，你指的是哪一种？',
  options: [
    { id: 'replan', label: '纳入明日整体重排', route_to: 'planning' },
    { id: 'insert', label: '插队到当前班次', route_to: 'scheduling' },
  ],
};

export const PLANNING_REPLY_TOKENS = [
  '已将 B 线明日目标设为 +20%（1,200 → 1,440 units）。',
  '约束求解后方案可行——装配二段为瓶颈，利用率 96%，交期可满足。',
  '详细参数与排程预览见右侧上下文面板。',
];

/* ---- Planning ---- */

const GANTT: GanttData = {
  resources: [{ id: 'LINE-B', name: 'B 线' }],
  tasks: [
    {
      id: 'T1',
      resource_id: 'LINE-B',
      order_id: 'WO-4821',
      start: '2026-06-27T08:00:00',
      end: '2026-06-27T12:00:00',
      type: 'production',
      label: 'WO-4821',
    },
    {
      id: 'T2',
      resource_id: 'LINE-B',
      order_id: 'WO-4830',
      start: '2026-06-27T12:00:00',
      end: '2026-06-27T12:45:00',
      type: 'changeover',
      label: 'A→B 换型',
    },
    {
      id: 'T3',
      resource_id: 'LINE-B',
      order_id: 'WO-4830',
      start: '2026-06-27T12:45:00',
      end: '2026-06-27T18:30:00',
      type: 'production',
      label: 'WO-4830',
    },
  ],
};

export const SOLVE_RUN_FEASIBLE: SolveRun = {
  solve_run_id: 'run-4821',
  status: 'feasible',
  kpis: { due_rate: 0.95, makespan_hours: 10.5, changeover_count: 2 },
  gantt: GANTT,
  baseline_gantt: null,
  explanation: '本方案优先保交期；相比规则基线换型减少 1 次，装配二段利用率提升至 96%。',
  infeasible_report: null,
};

export const SOLVE_RUNS: SolveRun[] = [
  SOLVE_RUN_FEASIBLE,
  {
    solve_run_id: 'run-4810',
    status: 'feasible',
    kpis: { due_rate: 0.91, makespan_hours: 11.2, changeover_count: 3 },
    gantt: GANTT,
    baseline_gantt: null,
    explanation: '上一版本：换型 3 次，综合利用率略低。',
    infeasible_report: null,
  },
];

/* ---- Scheduling ---- */

export const KITTING: KittingResponse = {
  items: [
    { work_order: 'WO-4830', material_rate: 1.0, tooling_rate: 1.0, status: 'ready', missing: [] },
    {
      work_order: 'WO-4836',
      material_rate: 0.89,
      tooling_rate: 1.0,
      status: 'partial',
      missing: [{ material: '包材-330', qty_short: 50 }],
    },
    {
      work_order: 'WO-4840',
      material_rate: 0.75,
      tooling_rate: 0.75,
      status: 'blocked',
      missing: [{ material: '夹具-B12', qty_short: 1 }],
    },
  ],
};

export const DISPATCH_ORDERS: DispatchOrdersResponse = {
  orders: [
    {
      id: 'WO-4830',
      line: 'LINE-B',
      summary: '插队至当前班次，触发 A→B 换型',
      authorization: 'requires_confirmation',
      action: { kind: 'insert', work_order: 'WO-4830', changeover: 'A→B' },
    },
    {
      id: 'WO-4836',
      line: 'LINE-B',
      summary: '顺延 1h 并通知装配三段',
      authorization: 'requires_confirmation',
      action: { kind: 'defer', work_order: 'WO-4836', minutes: 60 },
    },
    {
      id: 'WO-4815',
      line: 'LINE-B',
      summary: '续产任务，节拍不变',
      authorization: 'auto',
      action: { kind: 'continue', work_order: 'WO-4815' },
    },
  ],
};

export const EXCEPTION_IMPACT: ExceptionImpactResponse = {
  trigger: '3 号线设备报警 ALM-2207',
  affected_orders: ['WO-4830', 'WO-4836', 'WO-4840'],
  suggested_actions: [
    {
      label: '改派至 2 号线',
      authorization: 'requires_confirmation',
      action: { kind: 'reassign', from: 'LINE-03', to: 'LINE-02' },
    },
  ],
};

/* ---- Query (RAG) ---- */

export const QUERY_ANSWER_TOKENS = [
  'B 线当前 WIP 880 件；',
  '今日计划 1,200、已完成 1,032，达成率 86%。',
  '近 30 日班产峰值 1,460 件、平均 1,210 件。',
];

export const RAG_SOURCES: RagSource[] = [
  {
    id: 'src1',
    doc_name: 'MES 实时看板导出',
    section: 'B 线 / 今日 / 14:30',
    snippet: 'WIP 880 · 计划 1,200 · 完成 1,032 · 达成率 86%（14:30 采集）',
    relevance: 0.94,
  },
  {
    id: 'src2',
    doc_name: '产能基线分析报告 Q2',
    section: '§4.2 产线产能基线 · 附表 3',
    snippet: '近 30 日班产峰值 1,460、均值 1,210，满足 1,440 上限需求。',
    relevance: 0.88,
  },
];

/* ---- Knowledge base (RAG CRUD) ----
   Mutable in-memory store so the dev UI can add/rename/replace/delete without
   a backend. Seeded to mirror the backend's data/mock/knowledge/ files. */

export const KNOWLEDGE_SUPPORTED_EXTENSIONS = [
  '.md',
  '.markdown',
  '.txt',
  '.csv',
  '.html',
  '.pdf',
  '.docx',
];

export const KNOWLEDGE_DOCS: KnowledgeDoc[] = [
  {
    doc_id: 'seed_kitting-definition',
    name: 'kitting-definition.md',
    type: 'md',
    chunk_count: 4,
    bytes: 1192,
    status: 'ready',
    added_at: '2026-07-01T02:15:00Z',
  },
  {
    doc_id: 'seed_scheduling-concepts',
    name: 'scheduling-concepts.md',
    type: 'md',
    chunk_count: 6,
    bytes: 1339,
    status: 'ready',
    added_at: '2026-07-01T02:15:00Z',
  },
  {
    doc_id: 'seed_exception-handling',
    name: 'exception-handling.md',
    type: 'md',
    chunk_count: 5,
    bytes: 1722,
    status: 'ready',
    added_at: '2026-07-01T02:15:00Z',
  },
];

/* ---- Skills (skill package registry CRUD) ----
   Mutable in-memory store so the dev UI can import/delete without a backend.
   Seeded with two demo skills mirroring the backend's skills/ directory. */

export const SKILLS: SkillMeta[] = [
  {
    name: 'capacity-report',
    display_name: '产能日报',
    description: '汇总当日产能与瓶颈',
    when_to_use: ['给我出一份今天的产能报告'],
    allowed_tools: ['query_orders', 'query_work_orders'],
    user_invocable: true,
    disable_model_invocation: false,
    tool_preconditions: {},
    version: '1.0',
    author: 'demo',
    file_count: 0,
    bytes: 0,
    added_at: '2026-07-05T00:00:00Z',
  },
  {
    name: 'changeover-checklist',
    display_name: '换线检查清单',
    description: '换线前齐套与产线核对',
    when_to_use: ['3号线换线前检查'],
    allowed_tools: ['query_work_orders', 'check_kitting'],
    user_invocable: true,
    disable_model_invocation: false,
    tool_preconditions: {},
    version: '1.0',
    author: 'demo',
    file_count: 0,
    bytes: 0,
    added_at: '2026-07-05T00:00:00Z',
  },
];

/* ---- Audit ---- */

export const AUDIT_TIMELINE: AuditTimelineResponse = {
  events: [
    { ts: '2026-06-27T06:30:00Z', type: 'route', summary: '路由判定 → planning (0.92)', detail: { source: 'llm' } },
    { ts: '2026-06-27T06:30:02Z', type: 'llm_call', summary: 'LLM 结构化分类', detail: { model: 'gpt-4o-mini' } },
    { ts: '2026-06-27T06:30:05Z', type: 'engine_action', summary: 'planning.solve → feasible', detail: { run: 'run-4821' } },
  ],
};
