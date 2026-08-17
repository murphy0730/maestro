"""Conversation session endpoints."""

import asyncio
from functools import partial

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from maestro.runtime.models import RunStatus

router = APIRouter()

_TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


def _list_reconciled_sessions(platform):
    """Repair a stale session pointer from the durable Run truth on read."""
    sessions = platform.session_store.list_all()
    changed = False
    for session in sessions:
        if session.active_run_id is None:
            continue
        try:
            terminal = platform.run_store.load(session.active_run_id).status in _TERMINAL_RUN_STATUSES
        except (FileNotFoundError, ValueError):
            terminal = True
        if terminal:
            platform.session_store.clear_active_run(session.session_id, session.active_run_id)
            changed = True
    return platform.session_store.list_all() if changed else sessions


class CreateSessionRequest(BaseModel):
    title: str = "新对话"


@router.get("/sessions")
async def list_sessions(request: Request):
    """列出所有历史会话（按最近更新倒序）。"""
    sessions = await asyncio.to_thread(_list_reconciled_sessions, request.app.state.platform)
    return [session.model_dump() for session in sessions]


@router.post("/sessions")
async def create_session(req: CreateSessionRequest, request: Request):
    """新建会话，返回会话元数据（含新生成的 session_id）。"""
    meta = await asyncio.to_thread(request.app.state.platform.session_store.create, req.title)
    return meta.model_dump()


class UpdateSessionRequest(BaseModel):
    title: str


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: UpdateSessionRequest, request: Request):
    """重命名会话。"""
    store = request.app.state.platform.session_store
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    await asyncio.to_thread(store.update_title, session_id, req.title.strip() or "新对话")
    return store.get(session_id).model_dump()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """删除会话及其消息历史。"""
    ok = await asyncio.to_thread(request.app.state.platform.session_store.delete, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True, "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    """获取指定会话的完整消息历史。"""
    return await asyncio.to_thread(request.app.state.platform.session_store.get_messages, session_id)


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_session_message(
    session_id: str, message_id: str, request: Request, cascade: bool = False
):
    """删除指定会话中的一条消息；cascade=true 时连带删除该轮的 AI 回复。"""
    deleted = await asyncio.to_thread(
        partial(
            request.app.state.platform.session_store.delete_message,
            session_id,
            message_id,
            cascade=cascade,
        )
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True, "session_id": session_id, "deleted_ids": deleted}
