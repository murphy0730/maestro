"""FastAPI 应用入口。

启动: uvicorn scheduling_platform.main:app --reload
启动时后台运行事件总线消费循环 + 定时巡检。
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from scheduling_platform.bootstrap import build_platform
from scheduling_platform.domain.models import SystemEvent
from scheduling_platform.engines.query.ingestor import DocumentNotFound
from scheduling_platform.foundation.loaders import UnsupportedFileType
from scheduling_platform.orchestrator.schemas import ChatResponse

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
    # 前端引擎选择: auto=自动路由；指定引擎则跳过路由直达 (支持"选定调度引擎"多轮对话)
    route: Literal["auto", "planning", "scheduling", "query"] = "auto"


EngineName = Literal["planning", "scheduling", "query"]


class ChatStreamRequest(BaseModel):
    """前端流式对话入口。current_engine 指定引擎 (会话粘性 / 前端选定引擎)。"""

    session_id: str = "default"
    message: str
    current_engine: EngineName | None = None


class ClarifyStreamRequest(BaseModel):
    """澄清回选，直达所选引擎并续流。"""

    session_id: str = "default"
    option_id: str
    route_to: EngineName


class ConfirmRequest(BaseModel):
    session_id: str = "default"
    action_id: str
    approved: bool


class EventRequest(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


@app.post("/chat")
async def chat(req: ChatRequest):
    """统一对话入口。route 指定引擎时跳过意图路由，直达该引擎。"""
    response = await app.state.platform.orchestrator.handle(
        req.session_id, req.message, route=req.route
    )
    return response.model_dump(mode="json")


# ── 流式对话 (SSE) —— 对齐前端契约 (route → token… → done | clarify | error) ──

# 内部 route_method → 前端契约 source；内部 intent "ambiguous" → 前端 "uncertain"
_SOURCE_MAP = {
    "forced": "command",
    "embedding": "embedding",
    "llm": "llm",
    "clarified": "clarified",
    "fallback": "llm",
}
# 澄清选项顺序固定对应三引擎 (与 orchestrator.CLARIFY_OPTIONS 对齐)
_CLARIFY_ROUTES: list[EngineName] = ["planning", "scheduling", "query"]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _contract_route(rd) -> dict:
    """内部 RouteDecision → 前端契约 RouteDecision 形状。"""
    return {
        "intent": "uncertain" if rd.intent == "ambiguous" else rd.intent,
        "confidence": rd.confidence,
        "source": _SOURCE_MAP.get(rd.route_method, "llm"),
        "entities": rd.entities,
        "reason": rd.reason,
        "is_composite": False,
        "steps": [],
    }


def _reply_chunks(text: str, size: int = 8) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


async def _sse_from_response(resp: ChatResponse) -> AsyncIterator[str]:
    """把一次 ChatResponse 编排为契约 SSE 帧序列。"""
    if resp.route is not None:
        yield _sse("route", _contract_route(resp.route))

    if resp.needs_clarification:
        options = [
            {"id": str(i + 1), "label": label, "route_to": _CLARIFY_ROUTES[i]}
            for i, label in enumerate(resp.options)
            if i < len(_CLARIFY_ROUTES)
        ]
        yield _sse("clarify", {"question": resp.reply, "options": options})
        yield _sse("done", {"message_id": f"msg-{uuid4().hex[:12]}"})
        return

    # 智能体已产出完整答复；按契约拆成 token 增量流出，营造逐字效果
    for chunk in _reply_chunks(resp.reply):
        yield _sse("token", {"delta": chunk})
        await asyncio.sleep(0.02)
    yield _sse("done", {"message_id": f"msg-{uuid4().hex[:12]}"})


@app.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    """流式统一对话入口。current_engine 指定引擎时跳过意图路由，直达该引擎。"""

    async def gen() -> AsyncIterator[str]:
        try:
            resp = await app.state.platform.orchestrator.handle(
                req.session_id, req.message, route=req.current_engine or "auto"
            )
            async for frame in _sse_from_response(resp):
                yield frame
        except Exception as e:  # noqa: BLE001 — 编排失败也要以 error 帧收口，不断流
            logger.exception("[CHAT-STREAM] 处理失败")
            yield _sse("error", {"error": {"code": "ORCHESTRATOR_ERROR", "message": str(e)}})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/chat/clarify")
async def chat_clarify(req: ClarifyStreamRequest):
    """澄清回选：按所选引擎直接路由暂存的原请求并续流。"""

    async def gen() -> AsyncIterator[str]:
        try:
            resp = await app.state.platform.orchestrator.resume_clarification(
                req.session_id, req.route_to
            )
            async for frame in _sse_from_response(resp):
                yield frame
        except Exception as e:  # noqa: BLE001
            logger.exception("[CHAT-CLARIFY] 处理失败")
            yield _sse("error", {"error": {"code": "ORCHESTRATOR_ERROR", "message": str(e)}})

    return StreamingResponse(gen(), media_type="text/event-stream")


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


# ── 知识库文档 CRUD (RAG 知识库前端增删改查) ─────────────────────
# embedding / llm 复用配置文件模型；此处只暴露文档管理，检索/生成仍在查询引擎内。

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 单文件上限 10MB


class RenameRequest(BaseModel):
    name: str


def _ingestor():
    return app.state.platform.ingestor


@app.get("/knowledge")
async def list_knowledge():
    """列出知识库全部文档 (供前端管理列表)。首次访问时惰性加载种子知识库。"""
    await _ingestor().seed_from_directory()
    docs = _ingestor().list_docs()
    return {
        "docs": [d.model_dump(mode="json") for d in docs],
        "supported_extensions": _ingestor().supported_extensions,
    }


@app.post("/knowledge")
async def add_knowledge(file: UploadFile = File(...)):
    """上传一个文件入库 (增)。类型不支持 → 415；过大 → 413。"""
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
    try:
        doc = await _ingestor().add_upload(file.filename or "untitled", data)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    return doc.model_dump(mode="json")


@app.put("/knowledge/{doc_id}")
async def update_knowledge(
    doc_id: str,
    file: UploadFile | None = File(None),
    name: str | None = Form(None),
):
    """改: 传 file 换内容，传 name 改显示名 (二者可其一)。"""
    try:
        if file is not None:
            data = await file.read()
            if len(data) > _MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
            doc = await _ingestor().replace(doc_id, file.filename or "untitled", data)
        elif name is not None:
            doc = _ingestor().rename(doc_id, name)
        else:
            raise HTTPException(status_code=400, detail="需提供 file 或 name")
    except DocumentNotFound as e:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}") from e
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    return doc.model_dump(mode="json")


@app.delete("/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str):
    """删除文档及其向量片段 (删)。"""
    try:
        removed = _ingestor().remove(doc_id)
    except DocumentNotFound as e:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}") from e
    return {"doc_id": doc_id, "removed_chunks": removed}


@app.get("/health")
async def health():
    if not hasattr(app.state, "platform"):
        raise HTTPException(status_code=503, detail="platform not ready")
    return {"status": "ok", "llm_available": app.state.platform.llm.available}
