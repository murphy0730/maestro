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
]


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
    return results[tool_name]


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
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "planning", "version": "1"},
                    },
                }
            )
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
