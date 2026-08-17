import type { RunStep, RunStatus } from '@/types/api/runs';

export type ActivityTone = 'neutral' | 'active' | 'success' | 'warning' | 'danger';

export interface RuntimeName {
  label: string;
  context?: string;
}

export interface ActivityPresentation {
  eventType: string;
  label: string;
  detail?: string;
  subject?: string;
  tone: ActivityTone;
  technical: boolean;
  raw: string;
  count: number;
}

const runtimeNames: Record<string, RuntimeName> = {
  'Apply the selected skill to the objective': {
    label: '执行任务所需能力',
    context: '执行计划',
  },
  'Verify the result and report remaining uncertainty': {
    label: '核验结果并整理答复',
    context: '执行计划',
  },
  tool_search: { label: '查找可用能力', context: '运行时' },
  load_skill: { label: '加载任务技能', context: '运行时' },
  get_current_plan: { label: '查看当前计划', context: '运行时' },
  get_result_detail: { label: '读取结果详情', context: '运行时' },
  read_artifact: { label: '读取任务产物', context: '运行时' },
  knowledge_search: { label: '搜索知识库', context: '知识库' },
  memory_search: { label: '搜索历史记忆', context: '记忆库' },
  task: { label: '执行任务步骤', context: '执行计划' },
  capability: { label: '执行任务能力', context: '运行时' },
  'whatif-planning': { label: 'What-if 排产技能', context: '技能' },
  mcp__planning__apply_whatif_patch: { label: '应用场景调整', context: '排产服务' },
  mcp__planning__compare_whatif_runs: { label: '对比推演结果', context: '排产服务' },
  mcp__planning__create_whatif_scenario: { label: '创建推演场景', context: '排产服务' },
  mcp__planning__describe_whatif_scenario: { label: '查看推演场景', context: '排产服务' },
  mcp__planning__diagnose_bottleneck: { label: '诊断生产瓶颈', context: '排产服务' },
  mcp__planning__get_planning_overview: {
    label: '获取排产方案概览',
    context: '排产服务',
  },
  mcp__planning__get_whatif_run: { label: '查看推演任务', context: '排产服务' },
  mcp__planning__list_planning_rules: { label: '查看排产规则', context: '排产服务' },
  mcp__planning__revert_whatif_patch: { label: '撤销场景调整', context: '排产服务' },
  mcp__planning__run_whatif_planning: { label: '执行 What-if 排产', context: '排产服务' },
  mcp__planning__search_planning_entities: { label: '查找排产对象', context: '排产服务' },
};

const actionWords: Record<string, string> = {
  get: '获取',
  list: '查看',
  search: '查找',
  query: '查询',
  create: '创建',
  run: '执行',
  compare: '对比',
  diagnose: '诊断',
  describe: '查看',
  apply: '应用',
  revert: '撤销',
  publish: '发布',
  read: '读取',
  write: '写入',
  load: '加载',
  dispatch: '派发',
};

const subjectWords: Record<string, string> = {
  planning: '排产',
  overview: '概览',
  rule: '规则',
  rules: '规则',
  result: '结果',
  detail: '详情',
  scenario: '场景',
  bottleneck: '瓶颈',
  schedule: '计划',
  order: '工单',
  inventory: '库存',
  artifact: '产物',
};

const serviceNames: Record<string, string> = {
  planning: '排产服务',
};

export function presentRuntimeName(raw: string): RuntimeName {
  const known = runtimeNames[raw];
  if (known) return known;

  if (raw.startsWith('mcp__')) {
    const [, server = 'external', operation = 'capability'] = raw.split('__', 3);
    return {
      label: presentIdentifier(operation),
      context: serviceNames[server] ?? `${presentIdentifier(server)}服务`,
    };
  }

  return { label: presentIdentifier(raw) };
}

function presentIdentifier(raw: string): string {
  const normalized = raw.replace(/-/g, '_');
  const words = normalized.split('_').filter(Boolean);
  if (words.length === 0) return '未命名操作';
  const [first, ...rest] = words;
  if (actionWords[first]) {
    const subject = rest.map((word) => subjectWords[word] ?? word).join('');
    return `${actionWords[first]}${subject || '操作'}`;
  }
  if (words.some((word) => subjectWords[word]))
    return words.map((word) => subjectWords[word] ?? word).join('');
  return raw.includes('_') || raw.includes('-') ? words.join(' ') : raw;
}

export function runStatusLabel(status: string): string {
  return (
    (
      {
        created: '已创建',
        running_fast: '快速运行中',
        structuring: '正在制定执行计划',
        running_structured: '受控运行中',
        waiting_approval: '等待审批',
        waiting_external: '等待外部系统',
        reconciling: '正在核对执行结果',
        cancelling: '正在取消',
        cancelled: '已取消',
        failed: '执行失败',
        completed: '已完成',
      } as Record<string, string>
    )[status] ?? presentIdentifier(status)
  );
}

export function stepStatusLabel(status: RunStep['status']): string {
  return (
    {
      pending: '待开始',
      ready: '准备就绪',
      waiting_approval: '等待审批',
      running: '正在执行',
      waiting_external: '等待外部系统',
      reconciling: '正在核对结果',
      succeeded: '已完成',
      failed: '执行失败',
      cancelled: '已取消',
      skipped: '已跳过',
    } satisfies Record<RunStep['status'], string>
  )[status];
}

export function friendlyRuntimeText(raw?: string): string {
  if (!raw) return '';
  const known: Record<string, string> = {
    write: '操作涉及写入，需要切换为受控执行',
    high_risk_write: '操作风险较高，需要切换为受控执行',
    side_effect_requires_controlled_execution: '操作会影响外部系统，需要受控执行',
    'capability is not allowed by the skill': '当前技能未授权此能力',
    capability_not_activated: '能力尚未加载',
    result_not_found: '未找到引用的结果',
    result_offset_out_of_range: '结果读取位置无效',
    cycle_detected: '检测到重复调用，执行已停止',
    capability_budget_exhausted: '已达到本次运行的能力调用上限',
    model_unavailable: '模型服务当前不可用',
    context_overflow: '任务上下文超过模型窗口',
    intent_selected: '已根据任务选择执行方式',
    model_final: 'Agent 已完成答复',
    approval_required: '操作需要审批后才能继续',
    approval_granted: '审批通过，继续执行',
    approval_rejected: '操作审批已拒绝',
    unknown_write_outcome: '外部写入结果暂时无法确认',
    cancel_requested: '用户请求取消运行',
    cancelled: '运行已取消',
    schema_input: '能力参数格式不正确',
    unknown_capability: '未找到所需能力',
    missing_executor: '能力执行器不可用',
  };
  if (raw.startsWith('capability_exception:')) return '能力执行过程中出现异常';
  if (raw.startsWith('capability_version_unavailable:')) return '所需能力版本当前不可用';
  if (raw.startsWith('unknown_evidence:')) return '答复引用了无法核验的信息';
  return known[raw] ?? presentIdentifier(raw);
}

const technicalEvents = new Set([
  'MODEL_TURN',
  'CONTEXT_BUILT',
  'CHECKPOINT_CREATED',
  'RUN_CREATED',
  'run.created',
]);

const controlCapabilities = new Set(['tool_search', 'load_skill']);

export function presentActivity(summary: string): ActivityPresentation {
  const [eventType = '', ...parts] = summary.split(' · ');
  const subject = parts[0];
  const rawDetail = parts.slice(1).join(' · ');
  const base = {
    eventType,
    subject,
    raw: summary,
    count: 1,
    technical: technicalEvents.has(eventType),
  };

  if (eventType === 'TOOL_CALL' || eventType === 'TOOL_RESULT') {
    const capability = presentRuntimeName(subject || 'capability');
    const status = eventType === 'TOOL_CALL' ? 'running' : rawDetail || 'succeeded';
    const tone: ActivityTone =
      status === 'running'
        ? 'active'
        : status === 'succeeded'
          ? 'success'
          : status === 'unknown'
            ? 'warning'
            : 'danger';
    const state =
      status === 'running'
        ? '正在执行'
        : status === 'succeeded'
          ? '已完成'
          : status === 'unknown'
            ? '结果待确认'
            : '未完成';
    return {
      ...base,
      label: capability.label,
      detail: [state, capability.context].filter(Boolean).join(' · '),
      tone,
      technical: controlCapabilities.has(subject),
    };
  }

  const simple: Record<
    string,
    { label: string; tone?: ActivityTone; detail?: string; technical?: boolean }
  > = {
    USER_MESSAGE: { label: '收到任务', tone: 'neutral' },
    ASSISTANT_MESSAGE: { label: '已生成最终答复', tone: 'success' },
    RUN_CREATED: { label: '创建运行', technical: true },
    'run.created': { label: '创建运行', technical: true },
    PLAN_CREATED: { label: '生成执行计划', tone: 'success' },
    PLAN_STEP_UPDATED: { label: '更新执行计划', tone: 'neutral' },
    TOOL_SEARCH: { label: '查找可用能力', tone: 'active', detail: subject },
    SKILL_ACTIVATED: {
      label: `启用${presentRuntimeName(subject || 'skill').label}`,
      tone: 'success',
    },
    APPROVAL_REQUESTED: { label: '请求操作审批', tone: 'warning' },
    APPROVAL_RESOLVED: { label: '审批已处理', tone: 'success' },
    EVIDENCE_RECALLED: { label: '检索参考信息', tone: 'active' },
    EVIDENCE_USED: { label: '引用已核验信息', tone: 'success' },
    ARTIFACT_CREATED: { label: '生成任务产物', tone: 'success' },
    'artifact.created': { label: '生成任务产物', tone: 'success' },
    MODEL_TURN: { label: '完成一次模型推理', technical: true },
    CONTEXT_BUILT: { label: '准备本轮上下文', technical: true },
    CHECKPOINT_CREATED: { label: '保存会话检查点', technical: true },
    ERROR: { label: '运行出现异常', tone: 'danger', detail: friendlyRuntimeText(subject) },
    'run.path_selected': { label: '选择执行路径', detail: pathLabel(subject) },
    'run.path_upgraded': { label: '切换为受控执行', tone: 'warning' },
    'run.controlled_started': { label: '开始受控执行', tone: 'active' },
    'run.waiting_approval': { label: '等待审批', tone: 'warning' },
    'run.waiting_external': { label: '等待外部系统', tone: 'warning' },
    'run.reconciling': { label: '核对执行结果', tone: 'warning' },
    'run.cancelling': { label: '正在取消运行', tone: 'warning' },
    'run.cancelled': { label: '运行已取消', tone: 'neutral' },
    'run.completed': { label: '运行已完成', tone: 'success' },
    'run.failed': { label: '运行失败', tone: 'danger', detail: friendlyRuntimeText(subject) },
    'step.started': {
      label: presentRuntimeName(subject || 'capability').label,
      tone: 'active',
      detail: '正在执行',
    },
    'step.succeeded': {
      label: presentRuntimeName(subject || 'capability').label,
      tone: 'success',
      detail: '已完成',
    },
    'step.failed': {
      label: presentRuntimeName(subject || 'capability').label,
      tone: 'danger',
      detail: '执行失败',
    },
  };

  if (eventType === 'RUN_STATUS_CHANGED') {
    const status = subject as RunStatus | undefined;
    const label =
      status === 'completed'
        ? '运行已完成'
        : status === 'failed'
          ? '运行失败'
          : status === 'cancelled'
            ? '运行已取消'
            : status
              ? runStatusLabel(status)
              : '运行状态已更新';
    return {
      ...base,
      label,
      detail: rawDetail ? friendlyRuntimeText(rawDetail) : undefined,
      tone:
        status === 'completed'
          ? 'success'
          : status === 'failed'
            ? 'danger'
            : status === 'waiting_approval' || status === 'reconciling'
              ? 'warning'
              : 'active',
      technical: false,
    };
  }

  const matched = simple[eventType];
  if (matched)
    return {
      ...base,
      label: matched.label,
      detail: matched.detail,
      tone: matched.tone ?? 'neutral',
      technical: matched.technical ?? base.technical,
    };

  return {
    ...base,
    label: presentIdentifier(eventType),
    detail: subject ? friendlyRuntimeText(subject) : undefined,
    tone: 'neutral',
  };
}

export function compactActivities(items: ActivityPresentation[]): ActivityPresentation[] {
  const compacted: ActivityPresentation[] = [];
  for (const item of items) {
    const previous = compacted.at(-1);
    if (
      item.eventType === 'TOOL_RESULT' &&
      previous?.eventType === 'TOOL_CALL' &&
      item.subject === previous.subject
    ) {
      compacted.pop();
    }
    const current = compacted.at(-1);
    if (
      current &&
      current.label === item.label &&
      current.detail === item.detail &&
      current.tone === item.tone
    ) {
      current.count += 1;
      continue;
    }
    compacted.push({ ...item });
  }
  return compacted;
}

function pathLabel(path?: string): string | undefined {
  if (path === 'fast') return '快速执行';
  if (path === 'structured') return '受控执行';
  return path ? friendlyRuntimeText(path) : undefined;
}
