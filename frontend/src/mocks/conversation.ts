import type { ChatMessageData, ClarifyOption } from '@/types';

/** Mock conversation thread. Mirrors the design export's demo dialogue. */

export const CLARIFY_OPTIONS: ClarifyOption[] = [
  {
    id: 'replan',
    label: '① 纳入明日整体重排',
    desc: '与现有工单一起重新求解最优顺序',
    route: 'planning',
  },
  {
    id: 'insert',
    label: '② 插队到当前班次',
    desc: '立即下发，触发一次 A→B 换型（45min）',
    route: 'scheduling',
  },
];

export const MOCK_THREAD: ChatMessageData[] = [
  { id: 'm0', kind: 'system', text: '今天 · 6 月 25 日 · 周四' },
  {
    id: 'm1',
    kind: 'user',
    time: '14:30',
    text: '把 B 线明天的目标产量提高 20%，看看排程能不能扛得住。',
  },
  {
    id: 'm2',
    kind: 'agent',
    time: '14:30',
    route: 'planning',
    confidence: 0.92,
    reason: '目标产量调整属计划层重排，需重新求解产能约束',
    handoff: true,
    text: '已将 B 线明日目标设为 +20%（1,200 → 1,440 units）。约束求解后方案可行——装配二段为瓶颈，利用率 96%，交期可满足。详细参数与排程预览见右侧上下文面板。',
  },
  {
    id: 'm3',
    kind: 'user',
    time: '14:33',
    text: 'WO-4830 这张急单，先给它安排上。',
  },
  {
    id: 'm4',
    kind: 'clarify',
    time: '14:33',
    confidence: 0.41,
    reason: '意图可指向多个执行动作，置信不足以自动路由',
    question: '「先安排上 WO-4830」有两种执行方式，你指的是哪一种？',
    detail: '该工单交期紧但当前未排程。两种方式影响范围不同，请你确认动作类型。',
    options: CLARIFY_OPTIONS,
  },
];
