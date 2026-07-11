"""Chat and streaming conversation endpoints."""

import asyncio
import json
import logging
from typing import AsyncIterator, Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from maestro.foundation.exec_context import ExecMode
from maestro.orchestrator.schemas import ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()

EngineName = Literal["planning", "scheduling", "query"]


class ChatAttachment(BaseModel):
    name: str = Field(max_length=255)
    content_type: str = Field(default="text/plain", max_length=100)
    content: str = Field(max_length=1_048_576)
    size: int = Field(ge=0, le=1_048_576)


class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str
    route: Literal["auto", "planning", "scheduling", "query"] = "auto"
    skill_id: str | None = None
    skill_ids: list[str] | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=10)
    mode: ExecMode = "plan"


class ChatStreamRequest(BaseModel):
    session_id: str = "default"
    message: str
    current_engine: EngineName | None = None
    skill_id: str | None = None
    skill_ids: list[str] | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=10)
    mode: ExecMode = "plan"


class ClarifyStreamRequest(BaseModel):
    session_id: str = "default"
    option_id: str
    route_to: EngineName
    mode: ExecMode = "plan"


class ConfirmRequest(BaseModel):
    session_id: str = "default"
    action_id: str
    approved: bool


def _message_with_attachments(message: str, attachments: list[ChatAttachment]) -> str:
    if not attachments:
        return message
    blocks = []
    for item in attachments:
        safe_name = item.name.replace("\n", " ").replace("\r", " ")
        blocks.append(
            f"<attachment name={json.dumps(safe_name, ensure_ascii=False)}>\n"
            f"{item.content}\n</attachment>"
        )
    prefix = f"{message}\n\n用户同时提供了以下附件，请把它们作为参考资料：\n"
    return prefix + "\n\n".join(blocks)


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """统一对话入口。route 指定引擎时跳过意图路由，直达该引擎。"""
    response = await request.app.state.platform.orchestrator.handle(
        req.session_id,
        _message_with_attachments(req.message, req.attachments),
        route=req.route,
        skill_ids=req.skill_ids or ([req.skill_id] if req.skill_id else None),
        mode=req.mode,
    )
    return response.model_dump(mode="json")


_SOURCE_MAP = {
    "forced": "command",
    "embedding": "embedding",
    "llm": "llm",
    "clarified": "clarified",
    "fallback": "llm",
}
_CLARIFY_ROUTES: list[EngineName] = ["planning", "scheduling", "query"]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _progress_frames(task: asyncio.Task, q: "asyncio.Queue[str]") -> AsyncIterator[str]:
    """编排任务运行期间实时产出 progress 帧，任务结束后清空余量。"""
    while not task.done():
        getter = asyncio.ensure_future(q.get())
        done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            yield _sse("progress", {"text": getter.result()})
        else:
            getter.cancel()
    while not q.empty():
        yield _sse("progress", {"text": q.get_nowait()})


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
        "skill_id": rd.skill_id if rd.intent == "skill" else None,
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

    steps = resp.data.get("steps")
    if steps:
        yield _sse(
            "context",
            {
                "engine": "scheduling",
                "payload": {"steps": steps, "stop_reason": resp.data.get("stop_reason")},
            },
        )

    for chunk in _reply_chunks(resp.reply):
        yield _sse("token", {"delta": chunk})
        await asyncio.sleep(0.02)
    pending = [a for a in resp.pending_actions if a.status == "pending"]
    if pending:
        yield _sse("actions", {"actions": [a.model_dump(mode="json") for a in pending]})
    yield _sse("done", {"message_id": f"msg-{uuid4().hex[:12]}"})


_TITLE_SYSTEM = (
    "你是会话标题生成助手。根据用户的第一句话，生成一个简短、有意义的中文标题，"
    "用于会话列表展示。要求：概括核心意图；不超过 12 个汉字；"
    "只输出标题本身，不要标点、引号、书名号或任何多余文字。"
)


async def _summarize_title(platform, first_message: str) -> str | None:
    """用 LLM 把首条消息浓缩成短标题；不可用或失败时保留截断标题。"""
    if not platform.llm.available:
        return None
    try:
        raw = await platform.llm.complete(
            _TITLE_SYSTEM, [{"role": "user", "content": first_message}]
        )
    except Exception:  # noqa: BLE001 — 标题生成失败不影响主流程
        logger.warning("[TITLE] LLM 标题生成失败，保留截断标题", exc_info=True)
        return None
    title = raw.strip().strip("《》「」\\\"'“”").splitlines()[0].strip() if raw else ""
    return title[:16] or None


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest, request: Request):
    """流式统一对话入口。current_engine 指定引擎时跳过意图路由。"""

    async def gen() -> AsyncIterator[str]:
        platform = request.app.state.platform
        store = platform.session_store
        meta = store.get(req.session_id)
        is_first_turn = meta is not None and meta.message_count == 0
        title_task = (
            asyncio.create_task(_summarize_title(platform, req.message)) if is_first_turn else None
        )
        progress_q: asyncio.Queue[str] = asyncio.Queue()
        handle_task = asyncio.create_task(
            platform.orchestrator.handle(
                req.session_id,
                _message_with_attachments(req.message, req.attachments),
                route=req.current_engine or "auto",
                on_progress=progress_q.put,
                skill_ids=req.skill_ids or ([req.skill_id] if req.skill_id else None),
                mode=req.mode,
            )
        )
        try:
            async for frame in _progress_frames(handle_task, progress_q):
                yield frame
            resp = await handle_task
            if title_task is not None:
                # Title generation is auxiliary. It must never delay delivery of
                # the actual answer when the title-model call is slow.
                def apply_title(task: asyncio.Task[str | None]) -> None:
                    if task.cancelled() or task.exception() is not None:
                        return
                    title = task.result()
                    if title:
                        store.update_title(req.session_id, title)

                title_task.add_done_callback(apply_title)
            async for frame in _sse_from_response(resp):
                yield frame
        except Exception as e:  # noqa: BLE001 — 编排失败也要以 error 帧收口，不断流
            handle_task.cancel()
            if title_task is not None and not title_task.done():
                title_task.cancel()
            logger.exception("[CHAT-STREAM] 处理失败")
            yield _sse("error", {"error": {"code": "ORCHESTRATOR_ERROR", "message": str(e)}})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/chat/clarify")
async def chat_clarify(req: ClarifyStreamRequest, request: Request):
    """澄清回选：按所选引擎直接路由暂存的原请求并续流。"""

    async def gen() -> AsyncIterator[str]:
        progress_q: asyncio.Queue[str] = asyncio.Queue()
        resume_task = asyncio.create_task(
            request.app.state.platform.orchestrator.resume_clarification(
                req.session_id, req.route_to, on_progress=progress_q.put, mode=req.mode
            )
        )
        try:
            async for frame in _progress_frames(resume_task, progress_q):
                yield frame
            resp = await resume_task
            async for frame in _sse_from_response(resp):
                yield frame
        except Exception as e:  # noqa: BLE001
            resume_task.cancel()
            logger.exception("[CHAT-CLARIFY] 处理失败")
            yield _sse("error", {"error": {"code": "ORCHESTRATOR_ERROR", "message": str(e)}})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/chat/confirm")
async def chat_confirm(req: ConfirmRequest, request: Request):
    """确认/拒绝待执行动作。"""
    response = await request.app.state.platform.orchestrator.confirm(
        req.session_id, req.action_id, req.approved
    )
    return response.model_dump(mode="json")
