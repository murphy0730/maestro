"""Deterministic planning-shaped stdio MCP server for Runtime integration tests."""

import json
import os
import sys


BUILTIN_RULES = (
    "EDD",
    "SPT",
    "LPT",
    "CR",
    "ATC",
    "FIFO",
    "MST",
    "PRIORITY",
    "KIT_AWARE",
    "BOTTLENECK",
    "COMPOSITE",
)

def _tool(
    name: str,
    description: str,
    *,
    properties: dict | None = None,
    required: tuple[str, ...] = (),
) -> dict:
    schema = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return {"name": name, "description": description, "inputSchema": schema}


TOOLS = [
    {
        "name": "list_planning_rules",
        "description": "只读查询系统支持的内置排产规则、规则说明及默认规则。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "run_rule_planning",
        "description": (
            "使用指定内置规则执行一次排产，并更新系统最近一次仿真结果。"
            "这是有副作用的执行操作，调用前应获得用户确认。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "enum": list(BUILTIN_RULES),
                    "description": "要使用的内置排产规则名称",
                }
            },
            "required": ["rule_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_planning_overview",
        "description": "查询候选排产方案数量和关键指标。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "compare_planning_solutions",
        "description": (
            "比较候选排产方案的全局 KPI 和逐机负荷排行榜。"
            "machine_utilization_ranking 不是瓶颈归因。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "search_planning_entities",
        "description": "按名称或编号搜索订单和工序。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "query": {"type": "string"},
                "scenario_id": {"type": "string"},
            },
            "required": ["entity_type"],
        },
    },
    {
        "name": "diagnose_bottleneck",
        "description": "按卡住延误订单的等待时长定位真实瓶颈机器。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "solution_id": {"type": "string"},
                "machine_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["solution_id"],
        },
    },
    {
        "name": "explain_order_delay",
        "description": "解释指定订单在指定方案中的延误成因。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "solution_id": {"type": "string"},
            },
            "required": ["order_id", "solution_id"],
        },
    },
    {
        "name": "get_order_planning",
        "description": "查询订单在候选方案中的工序和完工时间。",
        "inputSchema": {
            "type": "object",
            "properties": {"order_query": {"type": "string"}},
            "required": ["order_query"],
        },
    },
    {
        "name": "get_operation_planning",
        "description": "查询工序在候选方案中的计划时间和资源。",
        "inputSchema": {
            "type": "object",
            "properties": {"operation_query": {"type": "string"}},
            "required": ["operation_query"],
        },
    },
    _tool(
        "create_whatif_scenario",
        "新建一个只存在于内存中的排产 What-if 场景。",
        properties={"name": {"type": "string"}},
    ),
    _tool(
        "apply_whatif_patch",
        "向 What-if 场景追加一批经过校验的改动。",
        properties={
            "scenario_id": {"type": "string"},
            "patches": {"type": "array", "items": {"type": "object"}},
        },
        required=("scenario_id", "patches"),
    ),
    _tool(
        "describe_whatif_scenario",
        "回显场景改动、校验结果和落库确认令牌。",
        properties={"scenario_id": {"type": "string"}},
    ),
    _tool(
        "revert_whatif_patch",
        "撤销场景中最近的改动。",
        properties={
            "scenario_id": {"type": "string"},
            "count": {"type": "integer", "minimum": 1},
        },
        required=("scenario_id",),
    ),
    _tool(
        "run_whatif_planning",
        "在场景副本上运行一条或多条规则，并可同时运行现状基线。",
        properties={
            "scenario_id": {"type": "string"},
            "rule_names": {"type": "array", "items": {"type": "string"}},
            "include_baseline": {"type": "boolean"},
        },
        required=("scenario_id",),
    ),
    _tool(
        "get_whatif_run",
        "轮询 What-if 推演状态和结果。",
        properties={"run_id": {"type": "string"}},
        required=("run_id",),
    ),
    _tool(
        "compare_whatif_runs",
        "比较多次 What-if 推演的 KPI。",
        properties={
            "run_ids": {"type": "array", "items": {"type": "string"}},
            "metric_keys": {"type": "array", "items": {"type": "string"}},
        },
        required=("run_ids",),
    ),
    _tool(
        "apply_whatif_to_instance",
        "把用户明确确认的场景改动写入正式实例。",
        properties={
            "scenario_id": {"type": "string"},
            "confirm_token": {"type": "string"},
        },
        required=("scenario_id", "confirm_token"),
    ),
    _tool("get_scheduling_status", "查询统一排产五步工作流状态。"),
    _tool(
        "validate_planning_instance",
        "校验当前排产实例并更新校验快照。",
        properties={"force": {"type": "boolean"}},
    ),
    _tool("list_planning_objectives", "查询优化目标及精确求解支持的目标子集。"),
    _tool(
        "build_planning_context",
        "启动图谱与计算上下文构建。",
        properties={"force": {"type": "boolean"}},
    ),
    _tool(
        "start_planning_optimization",
        "启动后台多目标排产优化。",
        properties={
            "objective_keys": {"type": "array", "items": {"type": "string"}},
            "target_solution_count": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
            "baseline_rule_name": {"type": "string"},
            "cold_start": {"type": "boolean"},
            "seed": {"type": "integer"},
        },
    ),
    _tool(
        "get_planning_task",
        "查询图谱、优化或精确窗口后台任务。",
        properties={
            "task_type": {
                "type": "string",
                "enum": ["graph", "optimization", "exact_window"],
            },
            "task_id": {"type": "string"},
        },
        required=("task_type", "task_id"),
    ),
    _tool(
        "start_exact_window_optimization",
        "启动近期窗口精确求解。",
        properties={
            "window_hours": {"type": "number"},
            "objective_weights": {"type": "object"},
            "time_limit_seconds": {"type": "integer"},
            "baseline_rule_name": {"type": "string"},
        },
        required=("objective_weights",),
    ),
    _tool(
        "evaluate_order_insertion",
        "在完整基准排程上评估新订单插入。",
        properties={
            "base_source": {"type": "string"},
            "task_id": {"type": "string"},
            "solution_id": {"type": "string"},
            "strategy_id": {"type": "string"},
            "policy": {"type": "string"},
            "orders": {"type": "array", "items": {"type": "object"}},
            "operations": {"type": "array", "items": {"type": "object"}},
        },
        required=("orders", "operations"),
    ),
    _tool(
        "get_insertion_schedule",
        "按评估 run 查询插单后的排程明细。",
        properties={
            "run_id": {"type": "string"},
            "order_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
        required=("run_id",),
    ),
    _tool(
        "get_online_dispatch_status",
        "查询在线调度会话状态。",
        properties={"resource_limit": {"type": "integer"}},
    ),
    _tool(
        "control_online_dispatch",
        "启动、推进或调整在线调度会话。",
        properties={
            "action": {
                "type": "string",
                "enum": ["start", "advance", "breakdown", "repair", "reschedule"],
            },
            "rule_name": {"type": "string"},
            "delta_hours": {"type": "number"},
            "machine_id": {"type": "string"},
            "repair_at_hours": {"type": "number"},
        },
        required=("action",),
    ),
]


_WRITE_ANNOTATIONS = {
    "run_rule_planning": {"destructiveHint": True, "idempotentHint": True},
    "create_whatif_scenario": {"destructiveHint": False, "idempotentHint": False},
    "apply_whatif_patch": {"destructiveHint": False, "idempotentHint": False},
    "revert_whatif_patch": {"destructiveHint": False, "idempotentHint": False},
    "run_whatif_planning": {"destructiveHint": False, "idempotentHint": False},
    "apply_whatif_to_instance": {"destructiveHint": True, "idempotentHint": False},
    "validate_planning_instance": {"destructiveHint": False, "idempotentHint": True},
    "build_planning_context": {"destructiveHint": False, "idempotentHint": True},
    "start_planning_optimization": {"destructiveHint": False, "idempotentHint": False},
    "start_exact_window_optimization": {
        "destructiveHint": False,
        "idempotentHint": False,
    },
    "evaluate_order_insertion": {"destructiveHint": False, "idempotentHint": False},
    "control_online_dispatch": {"destructiveHint": True, "idempotentHint": False},
}

for tool in TOOLS:
    write_annotations = _WRITE_ANNOTATIONS.get(tool["name"])
    tool["annotations"] = {
        "readOnlyHint": write_annotations is None,
        "openWorldHint": False,
        **(write_annotations or {"idempotentHint": True}),
    }


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result_for(tool_name: str, arguments: dict) -> tuple[str, dict]:
    preview = [
        {
            "operation_id": f"OP-{index:04d}",
            "resource_id": "M-1",
            "start_time": float(index),
            "end_time": float(index + 1),
        }
        for index in range(1, 21)
    ]
    rule_name = str(arguments.get("rule_name") or "ATC").upper()
    results = {
        "list_planning_rules": (
            "系统支持 11 种内置排产规则，默认规则为 ATC",
            {
                "ok": True,
                "data": {
                    "rule_count": len(BUILTIN_RULES),
                    "rules": [
                        {
                            "rule_name": name,
                            "description": f"{name} 排产规则",
                            "is_default": name == "ATC",
                        }
                        for name in BUILTIN_RULES
                    ],
                },
            },
        ),
        "run_rule_planning": (
            f"已使用 {rule_name} 完成排产，共 21 道工序，返回前 20 条预览",
            {
                "ok": True,
                "data": {
                    "rule_name": rule_name,
                    "rule_description": f"{rule_name} 排产规则",
                    "metrics": {"total_tardiness": 2.5, "makespan": 21.0},
                    "operation_count": 21,
                    "planning_preview": preview,
                    "planning_truncated": True,
                    "latest_simulation_updated": True,
                },
            },
        ),
        "get_planning_overview": (
            "当前有 2 个候选排产方案",
            {"ok": True, "candidate_count": 2, "archive_size": 4},
        ),
        "compare_planning_solutions": (
            "已比较 2 个候选方案",
            {
                "ok": True,
                "metric_scope": "solution_global",
                "ranking_scope": "per_machine",
                "solutions": [
                    {
                        "solution_id": "S-1",
                        "machine_utilization_ranking": [
                            {
                                "machine_id": "M-1",
                                "full_horizon_utilization": 0.8,
                                "utilization_scope": "full_horizon",
                            }
                        ],
                    },
                    {"solution_id": "S-2", "machine_utilization_ranking": []},
                ],
            },
        ),
        "search_planning_entities": (
            "找到 1 个匹配工序",
            {"ok": True, "items": [{"operation_id": "OP-1", "name": "Turning"}]},
        ),
        "diagnose_bottleneck": (
            "方案一等待主因是产能不足，M-1 是首要瓶颈",
            {
                "ok": True,
                "solution_id": "S-1",
                "wait_breakdown": {
                    "capacity_bound": 8.0,
                    "dispatch_bound": 1.0,
                    "off_shift": 2.0,
                    "downtime": 0.0,
                    "idle": 0.0,
                },
                "machines": [{"machine_id": "M-1", "capacity_wait_hours": 8.0}],
            },
        ),
        "explain_order_delay": (
            "订单 ORD-0004 延误 3 小时，主要是班次外等待",
            {
                "ok": True,
                "order_id": "ORD-0004",
                "planned": True,
                "tardiness_hours": 3.0,
                "inevitable_tardiness_hours": 0.0,
                "attribution": {"off_shift": 2.5},
            },
        ),
        "get_order_planning": (
            "已查询订单 ORD-0004",
            {"ok": True, "order_id": "ORD-0004", "operation_count": 2},
        ),
        "get_operation_planning": (
            "已查询工序 OP-0004-02-01",
            {"ok": True, "operation_id": "OP-0004-02-01", "planned": True},
        ),
    }
    return results.get(
        tool_name,
        (
            f"{tool_name} 已完成",
            {"ok": True, "data": {"tool": tool_name, "arguments": arguments}},
        ),
    )


def main() -> None:
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "planning", "version": "2"},
                        "instructions": (
                            "统一排产 MCP：先检查状态，再按需校验、构图、排产、"
                            "What-if、插单或在线调度。"
                        ),
                    },
                }
            )
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            if os.environ.get("PLANNING_FAIL_TOOL"):
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "isError": True,
                            "content": [
                                {"type": "text", "text": "PLANNING_API_UNAVAILABLE"}
                            ],
                        },
                    }
                )
                continue
            tool_name = request["params"]["name"]
            arguments = request["params"].get("arguments") or {}
            summary, data = result_for(tool_name, arguments)
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": summary}],
                        "structuredContent": data,
                    },
                }
            )


if __name__ == "__main__":
    main()
