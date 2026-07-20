"""Unified Run HTTP and resumable SSE endpoints."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from maestro.runtime.events import RunEvent
from maestro.runtime.models import RunRecord, RunStatus

router = APIRouter()


class CreateRunRequest(BaseModel):
    session_id: str = "default"
    message: str = Field(min_length=1)
    source: Literal["chat", "expert", "event", "resume"] = "chat"
    skill_names: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approved: bool
    expected_revision: int
    principal_id: str = "local-user"


def _error(status: int, code: str, message: str, run_id: str | None = None) -> HTTPException:
    detail: dict[str, str] = {"code": code, "message": message}
    if run_id is not None:
        detail["run_id"] = run_id
    return HTTPException(status, detail=detail)


def _dump_run(run: RunRecord) -> dict:
    return run.model_dump(mode="json")


@router.post("/runs", status_code=202)
async def create_run(payload: CreateRunRequest, request: Request):
    platform = request.app.state.platform
    try:
        platform.session_store.ensure(payload.session_id)
    except ValueError as error:
        raise _error(422, "invalid_session_id", str(error)) from error
    for artifact_id in payload.artifact_ids:
        try:
            platform.artifact_store.get(artifact_id)
        except (FileNotFoundError, ValueError):
            raise _error(404, "artifact_not_found", "artifact not found") from None
    run = await platform.runtime.create(
        payload.message, source=payload.source, requested_skills=payload.skill_names,
        session_id=payload.session_id,
        artifact_ids=payload.artifact_ids,
    )
    platform.session_store.append_message(
        payload.session_id, "user", payload.message,
        artifact_ids=payload.artifact_ids, skill_names=payload.skill_names,
    )
    platform.session_store.set_active_run(payload.session_id, run.run_id)
    async def execute_and_persist_reply() -> None:
        completed = await platform.runtime.execute(run.run_id)
        if completed.final_text:
            platform.session_store.append_run_final(completed.session_id, completed.run_id, completed.final_text)

    task = asyncio.create_task(execute_and_persist_reply())
    request.app.state.run_tasks.add(task)
    task.add_done_callback(request.app.state.run_tasks.discard)
    return _dump_run(run)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    try:
        return _dump_run(request.app.state.platform.run_store.load(run_id))
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found", run_id) from None


_EVENT_PROJECTION = {
    "model.turn": "token.delta",
    "write.started": "step.started",
    "capability.completed": "step.succeeded",
    "write.unknown": "run.reconciling",
    "approval.approved": "approval.resolved",
    "approval.requested": "approval.requested",
}


def _project(event: RunEvent) -> list[RunEvent]:
    """Expose stable v1 names without changing the durable internal Journal."""
    event_type = _EVENT_PROJECTION.get(event.type, event.type)
    if event.type == "capability.completed":
        event_type = "step.succeeded" if event.data.get("status") == "succeeded" else "step.failed"
    projected = event.model_copy(update={"type": event_type})
    if event.type != "approval.requested":
        return [projected]
    return [
        projected.model_copy(update={"event_id": f"{event.event_id}.waiting", "type": "run.waiting_approval"}),
        projected,
    ]


def _sse(event: RunEvent) -> str:
    return f"id: {event.event_id}\nevent: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False, default=str)}\n\n"


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    platform = request.app.state.platform
    try:
        platform.run_store.load(run_id)
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found", run_id) from None
    queue: asyncio.Queue[RunEvent] = asyncio.Queue()
    unsubscribe = platform.runtime._events.subscribe(
        lambda event: queue.put_nowait(event) if event.run_id == run_id else None
    )
    after = request.headers.get("Last-Event-ID")
    all_events = [item for event in platform.runtime._events.history(run_id) for item in _project(event)]
    known_ids = {event.event_id for event in all_events}
    events = all_events
    if after:
        found = next((index for index, event in enumerate(events) if event.event_id == after), None)
        events = events[found + 1 :] if found is not None else events

    async def body() -> AsyncIterator[str]:
        sent = set(known_ids)
        async def queued() -> AsyncIterator[str]:
            while not queue.empty():
                raw = queue.get_nowait()
                for event in _project(raw):
                    if event.event_id not in sent:
                        sent.add(event.event_id)
                        yield _sse(event)
        try:
            for event in events:
                yield _sse(event)
            terminal = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.WAITING_APPROVAL, RunStatus.RECONCILING}
            async for item in queued():
                yield item
            if platform.run_store.load(run_id).status in terminal:
                return
            while True:
                for event in _project(await queue.get()):
                    if event.event_id not in sent:
                        sent.add(event.event_id)
                        yield _sse(event)
                async for item in queued():
                    yield item
                if platform.run_store.load(run_id).status in terminal:
                    return
        finally:
            unsubscribe()

    return StreamingResponse(body(), media_type="text/event-stream")


@router.post("/runs/{run_id}/approvals/{approval_id}")
async def resolve_approval(run_id: str, approval_id: str, payload: ApprovalRequest, request: Request):
    try:
        run = await request.app.state.platform.runtime.approve(
            run_id, approval_id, payload.approved, payload.principal_id, payload.expected_revision
        )
    except FileNotFoundError:
        raise _error(404, "run_not_found", "run not found", run_id) from None
    except ValueError as error:
        raise _error(409, "stale_approval", str(error), run_id) from error
    return _dump_run(run)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request):
    try:
        return _dump_run(await request.app.state.platform.runtime.cancel(run_id))
    except (FileNotFoundError, ValueError):
        raise _error(404, "run_not_found", "run not found", run_id) from None
