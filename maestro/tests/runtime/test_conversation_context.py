"""The model must receive the current user message plus bounded session history."""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro.runtime.capabilities import CapabilityRegistry
from maestro.runtime.context import ContextProvider
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.models import RunStatus
from maestro.runtime.policy import PolicyGate
from maestro.runtime.store import ArtifactStore, RunStore
from fakes import FakeRuntimeModel


class StubHistory:
    """Stand in for SessionStore.get_messages, recording which session was asked for."""

    def __init__(self, messages: list[dict] | None = None, *, error: Exception | None = None) -> None:
        self._messages = messages or []
        self._error = error
        self.asked: list[str] = []

    def __call__(self, session_id: str) -> list[dict]:
        self.asked.append(session_id)
        if self._error is not None:
            raise self._error
        return list(self._messages)


def build_coordinator(
    tmp_path: Path,
    history: StubHistory | None = None,
    **kwargs: object,
) -> tuple[RunCoordinator, FakeRuntimeModel]:
    registry = CapabilityRegistry()
    model = FakeRuntimeModel()
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=EventPublisher(JsonlJournal(tmp_path / "journal.jsonl")),
        history_provider=history,
        **kwargs,
    )
    return coordinator, model


def stored(role: str, content: str, run_id: str | None = None) -> dict:
    return {"role": role, "content": content, "ts": "2026-01-01T00:00:00Z", "run_id": run_id}


@pytest.mark.asyncio
async def test_current_user_message_reaches_the_model(tmp_path: Path) -> None:
    coordinator, model = build_coordinator(tmp_path)
    model.queue_final("ok")

    await coordinator.start("记住数字 42")

    assert model.messages[0][-1] == {"role": "user", "content": "记住数字 42"}


@pytest.mark.asyncio
async def test_session_history_precedes_the_current_message(tmp_path: Path) -> None:
    history = StubHistory([stored("user", "记住数字 42"), stored("assistant", "好的，42。")])
    coordinator, model = build_coordinator(tmp_path, history)
    model.queue_final("42")

    await coordinator.start("我刚才让你记的数字是多少？", session_id="s1")

    assert history.asked == ["s1"]
    assert model.messages[0] == [
        {"role": "user", "content": "记住数字 42"},
        {"role": "assistant", "content": "好的，42。"},
        {"role": "user", "content": "我刚才让你记的数字是多少？"},
    ]


@pytest.mark.asyncio
async def test_current_turn_is_not_duplicated_from_history(tmp_path: Path) -> None:
    """The API appends the user message before execute(); it must not appear twice."""
    history = StubHistory()
    coordinator, model = build_coordinator(tmp_path, history)
    model.queue_final("ok")
    run = await coordinator.create("唯一的一条", session_id="s1")
    history._messages = [stored("user", "唯一的一条", run_id=run.run_id)]

    await coordinator.execute(run.run_id)

    assert model.messages[0] == [{"role": "user", "content": "唯一的一条"}]


@pytest.mark.asyncio
async def test_history_window_keeps_only_the_most_recent_turns(tmp_path: Path) -> None:
    history = StubHistory([stored("user", f"第{index}条") for index in range(10)])
    coordinator, model = build_coordinator(tmp_path, history, max_history_messages=4)
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert model.messages[0] == [
        {"role": "user", "content": "第6条"},
        {"role": "user", "content": "第7条"},
        {"role": "user", "content": "第8条"},
        {"role": "user", "content": "第9条"},
        {"role": "user", "content": "现在的问题"},
    ]


@pytest.mark.asyncio
async def test_unusable_history_entries_are_skipped(tmp_path: Path) -> None:
    history = StubHistory([
        stored("system", "内部提示"),
        stored("user", ""),
        stored("assistant", "有效回复"),
    ])
    coordinator, model = build_coordinator(tmp_path, history)
    model.queue_final("ok")

    await coordinator.start("问题", session_id="s1")

    assert model.messages[0] == [
        {"role": "assistant", "content": "有效回复"},
        {"role": "user", "content": "问题"},
    ]


@pytest.mark.asyncio
async def test_history_failure_degrades_instead_of_failing_the_run(tmp_path: Path) -> None:
    history = StubHistory(error=OSError("session file corrupted"))
    coordinator, model = build_coordinator(tmp_path, history)
    model.queue_final("ok")

    run = await coordinator.start("问题", session_id="s1")

    assert run.status is RunStatus.COMPLETED
    assert model.messages[0] == [{"role": "user", "content": "问题"}]


@pytest.mark.asyncio
async def test_child_runs_do_not_inherit_session_history(tmp_path: Path) -> None:
    """Child runs are isolated units; they carry only their own objective."""
    history = StubHistory([stored("user", "父会话历史")])
    coordinator, model = build_coordinator(tmp_path, history)
    model.queue_final("child done")
    parent = await coordinator.create("父任务", session_id="s1")
    child = parent.model_copy(update={"objective": "子任务"})

    await coordinator._run_controlled(
        child.model_copy(update={"status": RunStatus.RUNNING_STRUCTURED}),
        coordinator._capabilities.snapshot(),
        messages=[{"role": "user", "content": "子任务"}],
    )

    assert model.messages[0] == [{"role": "user", "content": "子任务"}]
