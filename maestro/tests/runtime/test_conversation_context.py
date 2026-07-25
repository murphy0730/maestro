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


class StubSummarizer:
    """Stand in for the LLM summarization boundary, recording every request."""

    def __init__(self, *, available: bool = True, error: Exception | None = None) -> None:
        self.available = available
        self._error = error
        self.calls: list[tuple[str, list[dict]]] = []

    async def summarize(self, prior_summary: str, turns: list[dict]) -> str:
        self.calls.append((prior_summary, list(turns)))
        if self._error is not None:
            raise self._error
        folded = "；".join(turn["content"] for turn in turns)
        return f"{prior_summary}+{folded}" if prior_summary else folded


class StubSummaryStore:
    """In-memory stand-in for SessionStore's summary sidecar."""

    def __init__(self, initial: dict[str, tuple[str, int]] | None = None) -> None:
        self.saved: dict[str, tuple[str, int]] = dict(initial or {})

    def get_summary(self, session_id: str) -> tuple[str, int]:
        return self.saved.get(session_id, ("", 0))

    def set_summary(self, session_id: str, summary: str, summarized_until: int) -> None:
        self.saved[session_id] = (summary, summarized_until)


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


def build_summarizing_coordinator(
    tmp_path: Path,
    messages: list[dict],
    *,
    summarizer: StubSummarizer | None = None,
    store: StubSummaryStore | None = None,
    window: int = 4,
    batch: int = 2,
) -> tuple[RunCoordinator, FakeRuntimeModel, StubSummarizer, StubSummaryStore]:
    summarizer = summarizer or StubSummarizer()
    store = store or StubSummaryStore()
    coordinator, model = build_coordinator(
        tmp_path,
        StubHistory(messages),
        max_history_messages=window,
        summarizer=summarizer,
        summary_store=store,
        summary_batch_messages=batch,
    )
    return coordinator, model, summarizer, store


def long_history(count: int = 10) -> list[dict]:
    return [stored("user", f"第{index}条") for index in range(count)]


@pytest.mark.asyncio
async def test_turns_outside_the_window_are_summarized_instead_of_dropped(tmp_path: Path) -> None:
    coordinator, model, summarizer, _ = build_summarizing_coordinator(tmp_path, long_history())
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    # The window still bounds the raw turns handed to the model.
    assert model.messages[0] == [
        {"role": "user", "content": "第6条"},
        {"role": "user", "content": "第7条"},
        {"role": "user", "content": "第8条"},
        {"role": "user", "content": "第9条"},
        {"role": "user", "content": "现在的问题"},
    ]
    assert [turn["content"] for turn in summarizer.calls[0][1]] == [f"第{n}条" for n in range(6)]
    assert "第0条" in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_summary_is_persisted_with_the_count_it_covers(tmp_path: Path) -> None:
    coordinator, model, _, store = build_summarizing_coordinator(tmp_path, long_history())
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert store.saved["s1"][1] == 6


@pytest.mark.asyncio
async def test_a_stored_summary_is_reused_without_another_model_call(tmp_path: Path) -> None:
    store = StubSummaryStore({"s1": ("早前的摘要", 6)})
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(), store=store
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert summarizer.calls == []
    assert "早前的摘要" in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_a_partial_batch_reuses_the_stored_summary(tmp_path: Path) -> None:
    """Summarizing costs a model call; one new stale turn is not worth it."""
    store = StubSummaryStore({"s1": ("早前的摘要", 5)})
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(), store=store, batch=2
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert summarizer.calls == []
    assert store.saved["s1"] == ("早前的摘要", 5)
    assert "早前的摘要" in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_a_new_batch_is_folded_into_the_prior_summary(tmp_path: Path) -> None:
    store = StubSummaryStore({"s1": ("早前的摘要", 4)})
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(), store=store
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert summarizer.calls[0][0] == "早前的摘要"
    assert [turn["content"] for turn in summarizer.calls[0][1]] == ["第4条", "第5条"]
    assert store.saved["s1"] == ("早前的摘要+第4条；第5条", 6)


@pytest.mark.asyncio
async def test_a_cursor_beyond_the_stale_turns_restarts_the_summary(tmp_path: Path) -> None:
    """Widening the window leaves the stored cursor meaningless; re-fold from zero."""
    store = StubSummaryStore({"s1": ("过期的摘要", 99)})
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(), store=store
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert summarizer.calls[0][0] == ""
    assert store.saved["s1"][1] == 6


@pytest.mark.asyncio
async def test_the_summary_reaches_the_model_as_untrusted_data(tmp_path: Path) -> None:
    coordinator, model, _, _ = build_summarizing_coordinator(tmp_path, long_history())
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert '<untrusted-data key="conversation-summary"' in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_an_unavailable_summarizer_falls_back_to_the_plain_window(tmp_path: Path) -> None:
    coordinator, model, summarizer, store = build_summarizing_coordinator(
        tmp_path, long_history(), summarizer=StubSummarizer(available=False)
    )
    model.queue_final("ok")

    run = await coordinator.start("现在的问题", session_id="s1")

    assert run.status is RunStatus.COMPLETED
    assert summarizer.calls == []
    assert store.saved == {}
    assert "conversation-summary" not in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_a_failing_summarizer_keeps_the_prior_summary_and_the_run(tmp_path: Path) -> None:
    store = StubSummaryStore({"s1": ("早前的摘要", 4)})
    coordinator, model, _, _ = build_summarizing_coordinator(
        tmp_path,
        long_history(),
        summarizer=StubSummarizer(error=RuntimeError("模型超时")),
        store=store,
    )
    model.queue_final("ok")

    run = await coordinator.start("现在的问题", session_id="s1")

    assert run.status is RunStatus.COMPLETED
    assert store.saved["s1"] == ("早前的摘要", 4)
    assert "早前的摘要" in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_sessions_shorter_than_the_window_are_never_summarized(tmp_path: Path) -> None:
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(3), window=4
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert summarizer.calls == []
    assert "conversation-summary" not in model.contexts[0].system_context


@pytest.mark.asyncio
async def test_a_zero_window_summarizes_every_prior_turn(tmp_path: Path) -> None:
    coordinator, model, summarizer, _ = build_summarizing_coordinator(
        tmp_path, long_history(3), window=0
    )
    model.queue_final("ok")

    await coordinator.start("现在的问题", session_id="s1")

    assert model.messages[0] == [{"role": "user", "content": "现在的问题"}]
    assert [turn["content"] for turn in summarizer.calls[0][1]] == ["第0条", "第1条", "第2条"]


@pytest.mark.asyncio
async def test_child_runs_are_never_summarized(tmp_path: Path) -> None:
    """A Child Run carries its own messages, so it must not touch session summaries."""
    coordinator, model, summarizer, _ = build_summarizing_coordinator(tmp_path, long_history())
    model.queue_final("child done")
    parent = await coordinator.create("父任务", session_id="s1")

    await coordinator._run_controlled(
        parent.model_copy(
            update={"objective": "子任务", "status": RunStatus.RUNNING_STRUCTURED}
        ),
        coordinator._capabilities.snapshot(),
        messages=[{"role": "user", "content": "子任务"}],
    )

    assert summarizer.calls == []
    assert "conversation-summary" not in model.contexts[0].system_context
