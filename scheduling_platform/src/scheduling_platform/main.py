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
from fastapi.middleware.cors import CORSMiddleware
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

# 允许 Web 前端与打包后的 Electron 应用 (file:// → Origin 为 null) 跨域访问。
# 本地部署场景放开全部来源；如需收紧，改为显式白名单。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


_TITLE_SYSTEM = (
    "你是会话标题生成助手。根据用户的第一句话，生成一个简短、有意义的中文标题，"
    "用于会话列表展示。要求：概括核心意图；不超过 12 个汉字；"
    "只输出标题本身，不要标点、引号、书名号或任何多余文字。"
)


async def _summarize_title(platform, first_message: str) -> str | None:
    """用 LLM 把首条消息浓缩成有意义的短标题；不可用或失败时返回 None（保留截断标题）。"""
    if not platform.llm.available:
        return None
    try:
        raw = await platform.llm.complete(
            _TITLE_SYSTEM, [{"role": "user", "content": first_message}]
        )
    except Exception:  # noqa: BLE001 — 标题生成失败不影响主流程
        logger.warning("[TITLE] LLM 标题生成失败，保留截断标题", exc_info=True)
        return None
    title = raw.strip().strip("《》「」\"'“”").splitlines()[0].strip() if raw else ""
    if not title:
        return None
    return title[:16]


@app.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    """流式统一对话入口。current_engine 指定引擎时跳过意图路由，直达该引擎。"""

    async def gen() -> AsyncIterator[str]:
        platform = app.state.platform
        store = platform.session_store
        meta = store.get(req.session_id)
        is_first_turn = meta is not None and meta.message_count == 0
        # 首轮：与编排并发生成标题，在流出任何帧之前落库，避免前端刷新竞态
        title_task = (
            asyncio.create_task(_summarize_title(platform, req.message))
            if is_first_turn
            else None
        )
        try:
            resp = await platform.orchestrator.handle(
                req.session_id, req.message, route=req.current_engine or "auto"
            )
            if title_task is not None:
                title = await title_task
                if title:
                    store.update_title(req.session_id, title)
            async for frame in _sse_from_response(resp):
                yield frame
        except Exception as e:  # noqa: BLE001 — 编排失败也要以 error 帧收口，不断流
            if title_task is not None and not title_task.done():
                title_task.cancel()
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


# ── 调度执行 + 决策时间线 (契约 §4.3 / §6，前端面板消费) ─────────


class ExecuteRequest(BaseModel):
    session_id: str = "default"
    action_id: str
    confirmed: bool = False


@app.post("/scheduling/execute")
async def scheduling_execute(req: ExecuteRequest):
    """执行一个待确认动作。走 ActionGate 统一闸口，两道写护栏不绕过。

    confirmed=false 不消费动作 (返回 pending 提示确认)；显式拒绝走 /chat/confirm。
    """
    platform = app.state.platform
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
    except ValueError as e:  # 已执行/已拒绝，不可重复处理
        raise HTTPException(status_code=409, detail=str(e)) from e
    ok = result is not None and result.success
    return {
        "status": "executed" if ok else "failed",
        "audit_id": action.action_id,
        "message": (result.detail if result else "") or action.description,
    }


# 审计 action → 契约时间线四分类；llm_call 当前不落审计，预留
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


def _timeline_summary(e) -> str:
    if e.action == "route" and e.result:
        return f"路由 → {e.result.get('intent')} ({e.result.get('method')}, 置信 {e.result.get('confidence')})"
    if e.authz_decision:
        return f"{e.action} [{e.authz_decision}]"
    return e.action


@app.get("/audit/timeline")
async def audit_timeline(session_id: str | None = None, limit: int = 100):
    """决策时间线 (契约 §6)。单用户版: 会话条目与全局系统条目 (巡检/事件) 合并返回。"""
    entries = app.state.platform.audit.query(limit=limit)
    if session_id:
        entries = [e for e in entries if e.actor == session_id or e.actor in _SYSTEM_ACTORS]
    return {
        "events": [
            {
                "ts": e.timestamp.isoformat(),
                "type": _timeline_type(e.action),
                "summary": _timeline_summary(e),
                "detail": {
                    "actor": e.actor,
                    "params": e.params,
                    "authz": e.authz_decision,
                    "result": e.result,
                },
            }
            for e in entries
        ]
    }


@app.get("/pending")
async def pending():
    """查询全部待确认动作。"""
    return [a.model_dump(mode="json") for a in app.state.platform.pending.list_pending()]


class CreateSessionRequest(BaseModel):
    title: str = "新对话"


@app.get("/sessions")
async def list_sessions():
    """列出所有历史会话（按最近更新倒序）。"""
    return [s.model_dump() for s in app.state.platform.session_store.list_all()]


@app.post("/sessions")
async def create_session(req: CreateSessionRequest):
    """新建会话，返回会话元数据（含新生成的 session_id）。"""
    meta = app.state.platform.session_store.create(req.title)
    return meta.model_dump()


class UpdateSessionRequest(BaseModel):
    title: str


@app.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: UpdateSessionRequest):
    """重命名会话。"""
    store = app.state.platform.session_store
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    store.update_title(session_id, req.title.strip() or "新对话")
    return store.get(session_id).model_dump()


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话及其消息历史。"""
    ok = app.state.platform.session_store.delete(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True, "session_id": session_id}


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定会话的完整消息历史。"""
    return app.state.platform.session_store.get_messages(session_id)


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
