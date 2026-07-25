"""排产查询能力桥接。

把外部排产应用 llm4drd（FastAPI，默认 http://localhost:8888）的只读查询端点
暴露为 Agent Runtime 的 TOOL，使前台「排产」模式下的 Agent 能够回答：
  - 某订单的排产情况（设备 / 起止时间 / 工期 / 是否延期）
  - 某工序的前一道（紧前）/ 后一道（紧后）工序是什么

这些端点均为只读 GET、不触发重排，因此注册为低风险、非写操作，走 Runtime 快路径、无需审批。
llm4drd 侧对应端点见 api/server.py 末尾的 /api/query/* 路由。
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from maestro.runtime.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)

_LLM4DRD_BASE_URL = os.environ.get("LLM4DRD_BASE_URL", "http://localhost:8888").rstrip("/")
_HTTP_TIMEOUT = float(os.environ.get("LLM4DRD_TIMEOUT", "30"))


async def _get_json(path: str) -> dict[str, Any]:
    url = f"{_LLM4DRD_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url, headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()


def _pick(call: "CapabilityCall", *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = call.arguments.get(key)
        if value not in (None, ""):
            return value
    return default


async def query_order_schedule(call: "CapabilityCall", _key: str | None) -> CapabilityResult:
    order_id = _pick(call, "order_id")
    if not order_id:
        return CapabilityResult(status="failed", error_message="缺少必填参数 order_id")
    try:
        data = await _get_json(f"/api/query/order/{order_id}/schedule")
    except httpx.HTTPStatusError as exc:
        return CapabilityResult(
            status="failed",
            error_message=f"排产应用返回错误 {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except Exception as exc:  # 连接失败 / 超时 / JSON 解析
        return CapabilityResult(status="failed", error_message=f"无法连接排产应用或解析失败: {exc}")
    return CapabilityResult(status="succeeded", content=data)


async def query_operation_predecessors(call: "CapabilityCall", _key: str | None) -> CapabilityResult:
    op_id = _pick(call, "operation_id", "op_id")
    if not op_id:
        return CapabilityResult(status="failed", error_message="缺少必填参数 operation_id")
    try:
        data = await _get_json(f"/api/query/operation/{op_id}/predecessors")
    except Exception as exc:
        return CapabilityResult(status="failed", error_message=f"查询前序工序失败: {exc}")
    return CapabilityResult(status="succeeded", content=data)


async def query_operation_successors(call: "CapabilityCall", _key: str | None) -> CapabilityResult:
    op_id = _pick(call, "operation_id", "op_id")
    if not op_id:
        return CapabilityResult(status="failed", error_message="缺少必填参数 operation_id")
    try:
        data = await _get_json(f"/api/query/operation/{op_id}/successors")
    except Exception as exc:
        return CapabilityResult(status="failed", error_message=f"查询后序工序失败: {exc}")
    return CapabilityResult(status="succeeded", content=data)


def register_scheduling_capabilities(platform: object) -> None:
    """在 bootstrap 中调用：把排产查询工具注册为 Runtime 的 TOOL。

    必须在 platform.refresh_skills() 之前调用，否则 scheduling-query 技能的
    allowed_tools 校验会找不到这些工具而抛 SkillValidationError。
    """
    registry: CapabilityRegistry = platform.capabilities  # type: ignore[attr-defined]
    specs = [
        CapabilitySpec(
            name="query-order-schedule",
            kind=CapabilityKind.TOOL,
            description=(
                "查询某订单的排产情况。参数 order_id 为订单编号（如 ORD-0001）。"
                "返回该订单各工序的设备、起止时间、工期、是否延期等排程明细。"
            ),
            input_schema={
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "订单编号"}},
                "required": ["order_id"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            idempotent=True,
            executor=query_order_schedule,
        ),
        CapabilitySpec(
            name="query-operation-predecessors",
            kind=CapabilityKind.TOOL,
            description=(
                "查询某道工序的前一道（紧前）工序。参数 operation_id 为工序编号（如 OP-0001-01-02）。"
                "返回前序工序的编号、名称与所属任务。"
            ),
            input_schema={
                "type": "object",
                "properties": {"operation_id": {"type": "string", "description": "工序编号"}},
                "required": ["operation_id"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            idempotent=True,
            executor=query_operation_predecessors,
        ),
        CapabilitySpec(
            name="query-operation-successors",
            kind=CapabilityKind.TOOL,
            description=(
                "查询某道工序的后一道（紧后）工序。参数 operation_id 为工序编号。"
                "返回后继工序的编号、名称与所属任务。"
            ),
            input_schema={
                "type": "object",
                "properties": {"operation_id": {"type": "string", "description": "工序编号"}},
                "required": ["operation_id"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            idempotent=True,
            executor=query_operation_successors,
        ),
    ]
    for spec in specs:
        registry.register(spec, replace=True)
