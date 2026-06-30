import type { AuthLevel, StatusKind } from '@/types';

/** Mock content for the three engine context panels. */

export const PLANNING_PANEL = {
  eyebrow: '排产引擎 · PLANNING ENGINE',
  title: 'B 线明日排产方案',
  strip: { title: '排产引擎已激活 · 方案就绪', meta: 'run #4821 · 约束求解 1.8s · 路由置信 0.92' },
  params: [
    { label: '目标产量', value: '1,440', unit: 'units', changed: true },
    { label: '原产量', value: '1,200', unit: 'units' },
    { label: '班次安排', value: '2', unit: '班' },
    { label: '换型次数', value: '2' },
    { label: '模具切换工时', value: '45', unit: 'min' },
    { label: '预计完工', value: '07-02 18:30' },
  ],
  capacity: [
    { name: '装配一段', used: 88 },
    { name: '装配二段', used: 96 },
    { name: '装配三段', used: 74 },
  ],
  badges: [
    { tone: 'success' as const, text: '交期可满足' },
    { tone: 'info' as const, text: '影响 3 张工单' },
    { tone: 'planning' as const, text: '产能峰值 1,460', glow: true },
  ],
};

export interface KitItem {
  name: string;
  sub: string;
  have: number;
  need: number;
  status: 'full' | 'partial' | 'missing';
}

export interface TaskOrder {
  id: string;
  desc: string;
  level: AuthLevel;
}

export const SCHEDULING_PANEL = {
  eyebrow: '调度引擎 · SCHEDULING ENGINE',
  title: 'B 线任务下发',
  strip: { title: '调度引擎已激活 · 待下发 5 条', meta: 'run #4827 · 齐套校验通过 · 路由置信 0.95' },
  kit: [
    { name: '主物料 BOM', sub: 'component / 关键件', have: 12, need: 12, status: 'full' },
    { name: '辅料 · 包材', sub: 'consumable', have: 8, need: 9, status: 'partial' },
    { name: '工装夹具', sub: 'fixture · 缺 1 关键', have: 3, need: 4, status: 'missing' },
    { name: '模具', sub: 'die · B 型已就位', have: 2, need: 2, status: 'full' },
  ] satisfies KitItem[],
  orders: [
    { id: 'WO-4830', desc: '插队至当前班次，触发 A→B 换型', level: 'confirm' },
    { id: 'WO-4836', desc: '顺延 1h 并通知装配三段', level: 'confirm' },
    { id: 'WO-4815', desc: '续产任务，节拍不变', level: 'auto' },
    { id: 'PREP-换型', desc: '模具 B 预热与点检指令', level: 'auto' },
  ] satisfies TaskOrder[],
};

export interface AnswerSegment {
  type: 'grounded' | 'inferred';
  cite?: number[];
  text: string;
}

export interface QuerySource {
  index: number;
  title: string;
  snippet: string;
  meta: string;
  score: number;
}

export const QUERY_PANEL = {
  eyebrow: '查询引擎 · QUERY ENGINE · RAG',
  title: 'B 线产能与达成率',
  strip: { title: '查询引擎已激活 · 检索 4 篇 · 命中 2', meta: 'run #4831 · RAG top-k=4 · 路由置信 0.97' },
  answer: [
    { type: 'grounded', cite: [1], text: 'B 线当前 WIP 880 件；今日计划 1,200、已完成 1,032，达成率 86%。' },
    { type: 'grounded', cite: [2], text: '近 30 日该线班产峰值 1,460 件，平均 1,210 件。' },
    {
      type: 'inferred',
      text: '按当前节拍与剩余 2.5h 推算，预计班末可达 ~1,180 件（≈98%），存在小幅缺口风险。',
    },
  ] satisfies AnswerSegment[],
  sources: [
    {
      index: 1,
      title: 'B 线实时看板快照',
      snippet: 'WIP 880 · 计划 1,200 · 完成 1,032 · 达成率 86%（14:30 采集）',
      meta: 'MES · board/B-line',
      score: 0.94,
    },
    {
      index: 2,
      title: 'B 线历史产能曲线',
      snippet: '近 30 日班产峰值 1,460、均值 1,210，满足 1,440 上限需求。',
      meta: 'SOP-203 · §4.2 附表',
      score: 0.88,
    },
  ] satisfies QuerySource[],
};

/** kit status → semantic tone + label */
export const KIT_STATUS: Record<KitItem['status'], { tone: StatusKind; label: string }> = {
  full: { tone: 'success', label: '齐套' },
  partial: { tone: 'warning', label: '部分' },
  missing: { tone: 'error', label: '缺料' },
};
