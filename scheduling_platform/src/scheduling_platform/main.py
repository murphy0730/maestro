"""FastAPI 应用入口。

启动: uvicorn scheduling_platform.main:app --reload
启动时后台运行事件总线消费循环 + 定时巡检。
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from scheduling_platform.bootstrap import build_platform
from scheduling_platform.domain.models import SystemEvent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform = build_platform()
    app.state.platform = platform
    bus_task = asyncio.create_task(platform.bus.run())
    patrol_task = asyncio.create_task(platform.patrol.run())
    logger.info("平台已启动: 事件总线 + 定时巡检运行中")
    try:
        yield
    finally:
        for task in (bus_task, patrol_task):
            task.cancel()


app = FastAPI(title="生产调度与排产 Agent 平台", version="0.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


class ConfirmRequest(BaseModel):
    session_id: str = "default"
    action_id: str
    approved: bool


class EventRequest(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


@app.post("/chat")
async def chat(req: ChatRequest):
    """统一对话入口。"""
    response = await app.state.platform.orchestrator.handle(req.session_id, req.message)
    return response.model_dump(mode="json")


@app.post("/chat/confirm")
async def chat_confirm(req: ConfirmRequest):
    """确认/拒绝待执行动作。"""
    response = await app.state.platform.orchestrator.confirm(
        req.session_id, req.action_id, req.approved
    )
    return response.model_dump(mode="json")


@app.post("/events")
async def inject_event(req: EventRequest):
    """手动注入系统事件 (测试事件驱动链路用)。"""
    event = SystemEvent(type=req.type, payload=req.payload)
    await app.state.platform.bus.publish(event)
    return {"queued": True, "event_id": event.event_id}


@app.get("/audit")
async def audit(action: str | None = None, limit: int = 100):
    """查询审计日志。"""
    entries = app.state.platform.audit.query(action=action, limit=limit)
    return [e.model_dump(mode="json") for e in entries]


@app.get("/pending")
async def pending():
    """查询全部待确认动作。"""
    return [a.model_dump(mode="json") for a in app.state.platform.pending.list_pending()]


@app.get("/health")
async def health():
    if not hasattr(app.state, "platform"):
        raise HTTPException(status_code=503, detail="platform not ready")
    return {"status": "ok", "llm_available": app.state.platform.llm.available}
