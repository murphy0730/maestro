import type { RouteEngine } from '@/types';

/** Mock top-bar / session state. */
export const MOCK_SESSION = {
  title: 'B 线产能 +20% 排产',
  user: '李工',
  role: '排产调度员',
  mesConnected: true,
};

/** Mock sidebar conversation history. `engine` tints the leading route dot. */
export interface ConversationSummary {
  id: string;
  title: string;
  engine: RouteEngine | null;
  time: string;
}

export const MOCK_CONVERSATIONS: ConversationSummary[] = [
  { id: 'c1', title: 'B 线产能 +20% 排产', engine: 'planning', time: '刚刚' },
  { id: 'c2', title: '注塑 2 号线锁模压力异常', engine: 'scheduling', time: '14:02' },
  { id: 'c3', title: 'WO-101 金属嵌件缺料查询', engine: 'query', time: '昨天' },
  { id: 'c4', title: 'A→B 换型节拍评估', engine: 'scheduling', time: '昨天' },
  { id: 'c5', title: '本周交期达成率复盘', engine: 'query', time: '6 月 24 日' },
];
