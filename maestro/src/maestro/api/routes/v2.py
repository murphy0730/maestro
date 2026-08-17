"""Canonical v2 API over the durable AgentEvent trajectory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from maestro.api.security import require_privileged
from maestro.foundation.sqlite_store import SQLiteStore, SessionBusy
from maestro.runtime.agent import AgentRuntime
from maestro.runtime.models import RunStatus
from maestro.runtime.trajectory import AgentEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2", tags=["agent-v2"])

_PAUSED_OR_TERMINAL = {
    RunStatus.WAITING_APPROVAL,
    RunStatus.RECONCILING,
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


def _runtime(request: Request) -> AgentRuntime:
    runtime = request.app.state.platform.runtime_v2
    if runtime is None:
        raise HTTPException(503, detail={"code": "runtime_unavailable"})
    return runtime


def _store(request: Request) -> SQLiteStore:
    store = request.app.state.platform.database
    if store is None:
        raise HTTPException(503, detail={"code": "runtime_unavailable"})
    return store


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _session_view(store: SQLiteStore, session) -> dict:
    return {
        **session.model_dump(mode="json"),
        "message_count": len(store.message_events(session.session_id)),
    }


def _run_view(store: SQLiteStore, run) -> dict:
    approvals = []
    if run.pending_approval_id:
        try:
            approval = store.get_approval(run.pending_approval_id)
            approvals = [
                {
                    **approval.model_dump(mode="json"),
                    "step_id": approval.tool_id,
                }
            ]
        except FileNotFoundError:
            pass
    task_statuses = {
        "pending": "pending",
        "ready": "ready",
        "in_progress": "running",
        "blocked": "waiting_external",
        "completed": "succeeded",
        "failed": "failed",
        "skipped": "skipped",
    }
    steps: dict[str, dict] = {}
    if run.current_plan_id:
        try:
            _, tasks = store.get_plan(run.current_plan_id)
            steps = {
                task.task_id: {
                    "step_id": task.task_id,
                    "kind": task.title,
                    "status": task_statuses[task.status.value],
                }
                for task in tasks
            }
        except FileNotFoundError:
            pass
    return {
        **run.model_dump(mode="json"),
        "steps": steps,
        "pending_approvals": approvals,
    }


def _track(request: Request, coroutine) -> None:
    task = asyncio.create_task(coroutine)
    request.app.state.run_tasks.add(task)

    def finished(done: asyncio.Task) -> None:
        request.app.state.run_tasks.discard(done)
        error = None if done.cancelled() else done.exception()
        if error is not None:
            logger.error(
                "v2 background run failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(finished)


class CreateSessionRequest(BaseModel):
    title: str = "新对话"


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CreateRunRequest(BaseModel):
    message: str = Field(min_length=1)
    source: Literal["chat", "expert", "event", "resume"] = "chat"
    requested_skills: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    principal_id: str = "local-user"
    max_steps: int = Field(default=24, ge=1, le=100)
    max_seconds: int = Field(default=600, ge=1, le=86_400)


class ApprovalRequest(BaseModel):
    approved: bool
    expected_revision: int = Field(ge=0)
    principal_id: str = "local-user"


class KnowledgeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    media_type: str = "text/plain"


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1)
    source: str = "user"


@router.get("/sessions")
async def list_sessions(request: Request):
    store = _store(request)
    return [_session_view(store, item) for item in store.list_sessions()]


@router.post("/sessions", status_code=201)
async def create_session(payload: CreateSessionRequest, request: Request):
    session = _runtime(request).create_session(payload.title.strip() or "新对话")
    return _session_view(_store(request), session)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    try:
        store = _store(request)
        return _session_view(store, store.get_session(session_id))
    except (FileNotFoundError, ValueError):
        raise _error(404, "session_not_found", "session not found") from None


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str, payload: RenameSessionRequest, request: Request
):
    try:
        store = _store(request)
        return _session_view(store, store.rename_session(session_id, payload.title.strip()))
    except (FileNotFoundError, ValueError):
        raise _error(404, "session_not_found", "session not found") from None


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    if not _store(request).delete_session(session_id):
        raise _error(404, "session_not_found", "session not found")
    return {"deleted": True, "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, request: Request):
    try:
        _store(request).get_session(session_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "session_not_found", "session not found") from None
    return [
        event.model_dump(mode="json")
        for event in _store(request).message_events(session_id)
    ]


@router.delete("/sessions/{session_id}/messages/{event_id}")
async def redact_message(
    session_id: str, event_id: str, request: Request, cascade: bool = False
):
    try:
        identifiers = _store(request).redact_message(
            session_id, event_id, cascade=cascade
        )
    except (FileNotFoundError, ValueError):
        raise _error(404, "message_not_found", "message not found") from None
    return {"redacted": True, "event_ids": identifiers}


@router.post("/sessions/{session_id}/runs", status_code=202)
async def create_run(session_id: str, payload: CreateRunRequest, request: Request):
    runtime = _runtime(request)
    for artifact_id in payload.artifact_ids:
        try:
            request.app.state.platform.artifact_store.get(artifact_id)
        except (FileNotFoundError, ValueError):
            raise _error(404, "artifact_not_found", "artifact not found") from None
    try:
        run = await runtime.create_run(
            session_id,
            payload.message,
            source=payload.source,
            requested_skills=payload.requested_skills,
            artifact_ids=payload.artifact_ids,
            principal_id=payload.principal_id,
            max_steps=payload.max_steps,
            max_seconds=payload.max_seconds,
        )
    except FileNotFoundError:
        raise _error(404, "session_not_found", "session not found") from None
    except SessionBusy:
        raise _error(409, "session_busy", "session already has an active run") from None
    except ValueError as error:
        raise _error(422, "invalid_run", str(error)) from error
    _track(request, runtime.execute(run.run_id))
    return _run_view(_store(request), run)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    try:
        store = _store(request)
        return _run_view(store, store.get_run(run_id))
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found") from None


def _sse(event: AgentEvent) -> str:
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event_type.value}\n"
        f"data: {event.model_dump_json()}\n\n"
    )


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    store = _store(request)
    runtime = _runtime(request)
    try:
        run = store.get_run(run_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found") from None

    queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
    unsubscribe = runtime.events.subscribe(
        lambda event: queue.put_nowait(event) if event.run_id == run_id else None
    )
    history = store.list_events(run.session_id, run_id=run_id, limit=10_000)
    already_seen: set[str] = set()
    after = request.headers.get("Last-Event-ID")
    if after:
        found = next(
            (index for index, event in enumerate(history) if event.event_id == after), None
        )
        if found is not None:
            already_seen.update(event.event_id for event in history[: found + 1])
            history = history[found + 1 :]

    async def body() -> AsyncIterator[str]:
        sent = set(already_seen)
        try:
            for event in history:
                sent.add(event.event_id)
                yield _sse(event)
            while True:
                while not queue.empty():
                    event = queue.get_nowait()
                    if event.event_id not in sent:
                        sent.add(event.event_id)
                        yield _sse(event)
                if store.get_run(run_id).status in _PAUSED_OR_TERMINAL:
                    for event in store.list_events(
                        run.session_id, run_id=run_id, limit=10_000
                    ):
                        if event.event_id not in sent:
                            sent.add(event.event_id)
                            yield _sse(event)
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event.event_id not in sent:
                    sent.add(event.event_id)
                    yield _sse(event)
        finally:
            unsubscribe()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/approvals/{approval_id}", status_code=202)
async def resolve_approval(
    run_id: str,
    approval_id: str,
    payload: ApprovalRequest,
    request: Request,
):
    store = _store(request)
    try:
        run = store.get_run(run_id)
        approval = store.get_approval(approval_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "approval_not_found", "approval not found") from None
    if (
        run.status is not RunStatus.WAITING_APPROVAL
        or run.pending_approval_id != approval_id
        or run.revision != payload.expected_revision
        or approval.status != "pending"
    ):
        raise _error(409, "stale_approval", "approval revision is stale")
    _track(
        request,
        _runtime(request).resolve_approval(
            run_id,
            approval_id,
            approved=payload.approved,
            principal_id=payload.principal_id,
            expected_revision=payload.expected_revision,
        ),
    )
    return {"accepted": True, "run_id": run_id, "approval_id": approval_id}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request):
    try:
        return _run_view(_store(request), await _runtime(request).cancel(run_id))
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found") from None


@router.get("/sessions/{session_id}/debug")
async def debug_session(session_id: str, request: Request):
    store = _store(request)
    try:
        session = store.get_session(session_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "session_not_found", "session not found") from None
    checkpoint = store.latest_checkpoint(session_id)
    return {
        "session": session.model_dump(mode="json"),
        "runs": [item.model_dump(mode="json") for item in store.list_runs(session_id)],
        "checkpoint": checkpoint.model_dump(mode="json") if checkpoint else None,
        "events": [
            item.model_dump(mode="json")
            for item in store.list_events(session_id, limit=10_000)
        ],
        "context_manifests": [
            item.model_dump(mode="json")
            for item in store.list_context_manifests(session_id)
        ],
    }


@router.get("/runs/{run_id}/debug")
async def debug_run(run_id: str, request: Request):
    store = _store(request)
    try:
        run = store.get_run(run_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found") from None
    plan = None
    if run.current_plan_id:
        current, tasks = store.get_plan(run.current_plan_id)
        plan = {
            "plan": current.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in tasks],
        }
    return {
        "run": _run_view(store, run),
        "events": [
            item.model_dump(mode="json")
            for item in store.list_events(run.session_id, run_id=run_id, limit=10_000)
        ],
        "plan": plan,
        "approvals": [
            item.model_dump(mode="json") for item in store.list_approvals(run_id)
        ],
        "context_manifests": [
            item.model_dump(mode="json")
            for item in store.list_context_manifests(run.session_id)
            if item.run_id == run_id
        ],
        "checkpoint": (
            checkpoint.model_dump(mode="json")
            if (checkpoint := store.latest_checkpoint(run.session_id))
            else None
        ),
    }


@router.get("/sessions/{session_id}/replay")
async def replay_session(session_id: str, request: Request):
    store = _store(request)
    try:
        session = store.get_session(session_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "session_not_found", "session not found") from None
    events = store.list_events(session_id, limit=10_000)
    errors: list[str] = []
    expected = 1
    for event in events:
        if event.sequence != expected:
            errors.append(f"event_sequence_gap:{expected}->{event.sequence}")
            expected = event.sequence
        expected += 1
    manifests = store.list_context_manifests(session_id)
    if any(item.prefix_hash != session.prefix_hash for item in manifests):
        errors.append("prefix_hash_mismatch")
    checkpoint = store.latest_checkpoint(session_id)
    if checkpoint and events and checkpoint.covered_until_sequence > events[-1].sequence:
        errors.append("checkpoint_beyond_event_stream")
    return {
        "valid": not errors,
        "errors": errors,
        "event_count": len(events),
        "last_sequence": events[-1].sequence if events else 0,
        "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None,
        "prefix_hash": session.prefix_hash,
        "context_hashes": [item.context_hash for item in manifests],
    }


@router.get("/knowledge")
async def list_knowledge(request: Request):
    return _store(request).list_knowledge_documents()


@router.post("/knowledge", status_code=201)
async def add_knowledge(
    payload: KnowledgeRequest,
    request: Request,
    _: str = Depends(require_privileged),
):
    document_id = _store(request).add_knowledge_document(
        title=payload.title, content=payload.content, media_type=payload.media_type
    )
    return {"document_id": document_id}


@router.delete("/knowledge/{document_id}")
async def delete_knowledge(
    document_id: str,
    request: Request,
    _: str = Depends(require_privileged),
):
    if not _store(request).delete_knowledge_document(document_id):
        raise _error(404, "document_not_found", "knowledge document not found")
    return {"deleted": True, "document_id": document_id}


@router.get("/memories")
async def list_memories(request: Request):
    return _store(request).list_memories()


@router.post("/memories", status_code=201)
async def add_memory(
    payload: MemoryRequest,
    request: Request,
    _: str = Depends(require_privileged),
):
    return {"memory_id": _store(request).add_memory(content=payload.content, source=payload.source)}


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    _: str = Depends(require_privileged),
):
    if not _store(request).delete_memory(memory_id):
        raise _error(404, "memory_not_found", "memory not found")
    return {"deleted": True, "memory_id": memory_id}
