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
        "description": "比较候选排产方案的总延误和完工跨度。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_planning_entities",
        "description": "按名称或编号搜索订单和工序。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["entity_type", "query"],
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
            {"ok": True, "solutions": [{"solution_id": "S-1"}, {"solution_id": "S-2"}]},
        ),
        "search_planning_entities": (
            "找到 1 个匹配工序",
            {"ok": True, "items": [{"operation_id": "OP-1", "name": "Turning"}]},
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
