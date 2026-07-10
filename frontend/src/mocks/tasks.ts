import type { GanttData, SolveKpis } from '@/types/api';

/**
 * Demo data for the task list page. The backend has no `GET /tasks` endpoint
 * yet, and this pass deliberately does not wire the gantt to a live `SolveRun`,
 * so the page reads from here. Shapes match `types/api.ts` exactly — wiring it
 * up later means swapping the data source, not touching the components.
 */

export type OrderStatus = 'running' | 'pending' | 'auto' | 'blocked';

export interface WorkOrder {
  id: string;
  desc: string;
  priority: 'urgent' | 'high' | 'normal';
  stage: string;
  /** `null` for preparation tasks that produce nothing. */
  qty: number | null;
  /** ISO datetime */
  due: string;
  status: OrderStatus;
}

export const TASKS_RUN = { id: 'run-4821', line: 'B 线', status: 'feasible' as const };

export const TASKS_KPIS: SolveKpis = {
  due_rate: 0.964,
  makespan_hours: 18.6,
  changeover_count: 2,
};

/** Deltas against the rule baseline, shown under each KPI. */
export const TASKS_KPI_DELTA = { due_rate: 4.2, makespan_hours: -1.9, changeover_count: 0 };

export const TASKS_GANTT: GanttData = {
  resources: [
    { id: 'RES-A1', name: '装配一段' },
    { id: 'RES-A2', name: '装配二段' },
    { id: 'RES-A3', name: '装配三段' },
    { id: 'RES-F1', name: '总装工位' },
  ],
  tasks: [
    // 装配一段：续产 → 换型 → 插队
    {
      id: 'T1',
      resource_id: 'RES-A1',
      order_id: 'WO-4815',
      start: '2026-07-02T08:00:00',
      end: '2026-07-02T12:00:00',
      type: 'production',
      label: 'WO-4815 续产',
    },
    {
      id: 'T2',
      resource_id: 'RES-A1',
      order_id: 'WO-4830',
      start: '2026-07-02T12:00:00',
      end: '2026-07-02T12:45:00',
      type: 'changeover',
      label: 'A→B 换型',
    },
    {
      id: 'T3',
      resource_id: 'RES-A1',
      order_id: 'WO-4830',
      start: '2026-07-02T12:45:00',
      end: '2026-07-02T17:30:00',
      type: 'production',
      label: 'WO-4830 插队',
    },
    // 装配二段：负载最高的一段
    {
      id: 'T4',
      resource_id: 'RES-A2',
      order_id: 'WO-4822',
      start: '2026-07-02T09:00:00',
      end: '2026-07-02T12:30:00',
      type: 'production',
      label: 'WO-4822',
    },
    {
      id: 'T5',
      resource_id: 'RES-A2',
      order_id: 'WO-4830',
      start: '2026-07-02T12:30:00',
      end: '2026-07-02T18:30:00',
      type: 'production',
      label: 'WO-4830 装配',
    },
    // 装配三段：中间插一次点检停机
    {
      id: 'T6',
      resource_id: 'RES-A3',
      order_id: 'WO-4822',
      start: '2026-07-02T10:00:00',
      end: '2026-07-02T12:45:00',
      type: 'production',
      label: 'WO-4822',
    },
    {
      id: 'T7',
      resource_id: 'RES-A3',
      order_id: 'PREP-换型',
      start: '2026-07-02T12:45:00',
      end: '2026-07-02T14:00:00',
      type: 'downtime',
      label: '模具点检',
    },
    {
      id: 'T8',
      resource_id: 'RES-A3',
      order_id: 'WO-4836',
      start: '2026-07-02T14:00:00',
      end: '2026-07-02T18:00:00',
      type: 'production',
      label: 'WO-4836 顺延',
    },
    // 总装工位：被缺料卡住
    {
      id: 'T9',
      resource_id: 'RES-F1',
      order_id: 'WO-4815',
      start: '2026-07-02T11:00:00',
      end: '2026-07-02T14:00:00',
      type: 'production',
      label: 'WO-4815',
    },
    {
      id: 'T10',
      resource_id: 'RES-F1',
      order_id: 'WO-4842',
      start: '2026-07-02T14:00:00',
      end: '2026-07-02T16:00:00',
      type: 'shortage',
      label: '缺工装夹具 FX-207',
    },
    {
      id: 'T11',
      resource_id: 'RES-F1',
      order_id: 'WO-4836',
      start: '2026-07-02T16:00:00',
      end: '2026-07-02T19:00:00',
      type: 'production',
      label: 'WO-4836',
    },
  ],
};

/** Where the "now" line sits on the demo gantt. */
export const TASKS_NOW = new Date('2026-07-02T13:00:00');

export const WORK_ORDERS: WorkOrder[] = [
  {
    id: 'WO-4830',
    desc: '插队至当前班次 · 触发 A→B 换型',
    priority: 'urgent',
    stage: '装配一 / 二段',
    qty: 480,
    due: '2026-07-02T18:30:00',
    status: 'pending',
  },
  {
    id: 'WO-4836',
    desc: '顺延 1h 并通知装配三段',
    priority: 'high',
    stage: '装配三段',
    qty: 320,
    due: '2026-07-02T21:00:00',
    status: 'pending',
  },
  {
    id: 'WO-4815',
    desc: '续产任务 · 节拍不变',
    priority: 'normal',
    stage: '装配一段',
    qty: 640,
    due: '2026-07-02T14:00:00',
    status: 'running',
  },
  {
    id: 'WO-4842',
    desc: '总装 · 等待工装夹具 FX-207',
    priority: 'urgent',
    stage: '总装工位',
    qty: 200,
    due: '2026-07-03T09:00:00',
    status: 'blocked',
  },
  {
    id: 'PREP-换型',
    desc: '模具 B 预热与点检指令',
    priority: 'normal',
    stage: '装配一段',
    qty: null,
    due: '2026-07-02T12:20:00',
    status: 'auto',
  },
];
