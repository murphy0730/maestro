"""Operations, audit, and observation endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from maestro.domain.models import SystemEvent

router = APIRouter()


class EventRequest(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


@router.post("/events")
async def inject_event(req: EventRequest, request: Request):
    """手动注入系统事件（测试事件驱动链路用）。"""
    event = SystemEvent(type=req.type, payload=req.payload)
    await request.app.state.platform.bus.publish(event)
    return {"queued": True, "event_id": event.event_id}


@router.get("/audit")
async def audit(request: Request, action: str | None = None, limit: int = 100):
    """查询审计日志。"""
    entries = request.app.state.platform.audit.query(action=action, limit=limit)
    return [entry.model_dump(mode="json") for entry in entries]


class ExecuteRequest(BaseModel):
    session_id: str = "default"
    action_id: str
    confirmed: bool = False


@router.post("/scheduling/execute")
async def scheduling_execute(req: ExecuteRequest, request: Request):
    """执行一个待确认动作。confirmed=false 时不消费动作。"""
    platform = request.app.state.platform
    if platform.pending.get(req.action_id) is None:
        raise HTTPException(status_code=404, detail=f"动作不存在: {req.action_id}")
    if not req.confirmed:
        return {
            "status": "pending",
            "audit_id": req.action_id,
            "message": "该动作需二次确认，请以 confirmed=true 重试；拒绝请走 /chat/confirm",
        }
    try:
        action, result = await platform.gate.confirm(req.action_id, True, actor=req.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    ok = result is not None and result.success
    return {
        "status": "executed" if ok else "failed",
        "audit_id": action.action_id,
        "message": (result.detail if result else "") or action.description,
    }


_SYSTEM_ACTORS = {"system", "scheduling_agent", "event_layer"}
_TOOL_ACTION_PREFIXES = (
    "dispatch_work_order",
    "send_expedite_message",
    "update_work_order_status",
    "send_notification",
    "precondition_blocked",
)


def _timeline_type(action: str) -> str:
    if action == "route":
        return "route"
    if action.startswith(_TOOL_ACTION_PREFIXES):
        return "tool_call"
    return "engine_action"


def _timeline_summary(entry) -> str:
    if entry.action == "route" and entry.result:
        return (
            f"路由 → {entry.result.get('intent')} "
            f"({entry.result.get('method')}, 置信 {entry.result.get('confidence')})"
        )
    if entry.authz_decision:
        return f"{entry.action} [{entry.authz_decision}]"
    return entry.action


@router.get("/audit/timeline")
async def audit_timeline(request: Request, session_id: str | None = None, limit: int = 100):
    """返回会话条目与全局系统条目合并后的决策时间线。"""
    entries = request.app.state.platform.audit.query(limit=limit)
    if session_id:
        entries = [entry for entry in entries if entry.actor == session_id or entry.actor in _SYSTEM_ACTORS]
    return {
        "events": [
            {
                "ts": entry.timestamp.isoformat(),
                "type": _timeline_type(entry.action),
                "summary": _timeline_summary(entry),
                "detail": {
                    "actor": entry.actor,
                    "params": entry.params,
                    "authz": entry.authz_decision,
                    "result": entry.result,
                },
            }
            for entry in entries
        ]
    }


@router.get("/pending")
async def pending(request: Request):
    """查询全部待确认动作。"""
    return [action.model_dump(mode="json") for action in request.app.state.platform.pending.list_pending()]


@router.get("/observations/{ref}")
async def get_observation(
    ref: str, request: Request, offset: int = 0, limit: int = 20, keys: str | None = None
):
    """懒加载一个被离线暂存的大工具观察。"""
    key_list = [key for key in keys.split(",") if key] if keys else None
    page = request.app.state.platform.observations.get(
        ref, offset=offset, limit=limit, keys=key_list
    )
    if "error" in page:
        raise HTTPException(status_code=404, detail=page["error"])
    return page
