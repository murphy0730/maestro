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
  start: string;
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
  baseline_gantt?: GanttData | null;
  explanation: string;
  infeasible_report?: InfeasibleReport | null;
}

export type SolveRunList = SolveRun[];
