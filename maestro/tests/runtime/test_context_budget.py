"""One token budget over both channels: system context, conversation, tools.

Before this, the system context had a character budget and the conversation had
none at all, so the channel that grew fastest — two messages per step, each up
to the artifact threshold — was the one nothing bounded.
"""

from __future__ import annotations

import json

from maestro.runtime.context import ContextItem, ContextProvider, Priority


def _spiller(store: dict[str, bytes]):
    def spill(payload: bytes) -> str:
        artifact_id = f"{len(store):064x}"
        store[artifact_id] = payload
        return artifact_id

    return spill


def _tool_message(index: int, size: int = 400) -> dict:
    return {
        "role": "tool",
        "tool_call_id": f"call_{index}",
        "content": json.dumps({"rows": "排产数据" * size}, ensure_ascii=False),
    }


def test_budget_reports_every_channel() -> None:
    provider = ContextProvider(max_chars=1000, base_system_prompt="你是 Maestro。")

    bundle = provider.assemble(
        [ContextItem(key="a", text="工单信息")],
        [{"role": "user", "content": "排产"}],
        [{"type": "function", "function": {"name": "read_file"}}],
    )

    assert bundle.budget.system_tokens > 0
    assert bundle.budget.messages_tokens > 0
    assert bundle.budget.tools_tokens > 0
    assert bundle.budget.total_tokens == (
        bundle.budget.system_tokens
        + bundle.budget.messages_tokens
        + bundle.budget.tools_tokens
    )


def test_conversation_is_untouched_when_it_fits() -> None:
    provider = ContextProvider(max_chars=1000, max_prompt_tokens=100_000)
    messages = [_tool_message(0), _tool_message(1)]

    bundle = provider.assemble([], messages, spill=_spiller({}))

    assert bundle.messages == messages
    assert bundle.budget.shed == ()


def test_oldest_tool_results_are_demoted_until_the_prompt_fits() -> None:
    store: dict[str, bytes] = {}
    provider = ContextProvider(
        max_chars=1000, max_prompt_tokens=4_000, keep_recent_tool_results=1
    )
    messages = [{"role": "user", "content": "排产"}] + [_tool_message(i) for i in range(6)]

    bundle = provider.assemble([], messages, spill=_spiller(store))

    assert bundle.budget.shed, "an over-budget conversation must be trimmed"
    demoted = [
        message
        for message in bundle.messages
        if message["role"] == "tool" and "artifact_ref" in message["content"]
    ]
    # Demotion runs oldest-first, so the survivor is the newest.
    assert bundle.messages[-1]["content"] == messages[-1]["content"]
    assert len(demoted) == len(store) == len(bundle.budget.shed)


def test_the_newest_tool_results_are_never_demoted() -> None:
    """Shedding what the model is still reasoning about strands it mid-thought."""
    provider = ContextProvider(
        max_chars=1000, max_prompt_tokens=1, keep_recent_tool_results=2
    )
    messages = [_tool_message(i) for i in range(4)]

    bundle = provider.assemble([], messages, spill=_spiller({}))

    assert bundle.messages[-2:] == messages[-2:]
    # Holding those back can leave the prompt over budget, and that is reported
    # rather than resolved by evicting them.
    assert bundle.budget.over_budget


def test_a_demoted_result_keeps_a_readable_reference() -> None:
    """The payload must stay recoverable; an evicted turn would not be."""
    store: dict[str, bytes] = {}
    provider = ContextProvider(
        max_chars=1000, max_prompt_tokens=1, keep_recent_tool_results=0
    )
    original = _tool_message(0)

    bundle = provider.assemble([], [original], spill=_spiller(store))

    envelope = json.loads(bundle.messages[0]["content"])
    assert envelope["artifact_ref"] in store
    assert store[envelope["artifact_ref"]].decode() == original["content"]
    assert "read_artifact" in envelope["message"]


def test_an_already_demoted_result_is_not_demoted_again() -> None:
    """Otherwise each turn would spill the envelope into a fresh artifact."""
    store: dict[str, bytes] = {}
    provider = ContextProvider(
        max_chars=1000, max_prompt_tokens=1, keep_recent_tool_results=0
    )

    once = provider.assemble([], [_tool_message(0)], spill=_spiller(store))
    twice = provider.assemble([], once.messages, spill=_spiller(store))

    assert twice.budget.shed == ()
    assert twice.messages == once.messages
    assert len(store) == 1


def test_budgeting_is_off_without_a_limit() -> None:
    """Callers that predate the budget keep the character bound and nothing else."""
    provider = ContextProvider(max_chars=1000)
    messages = [_tool_message(i) for i in range(6)]

    bundle = provider.assemble([], messages, spill=_spiller({}))

    assert bundle.messages == messages
    assert bundle.budget.limit == 0
    assert bundle.budget.over_budget is False


def test_budgeting_is_skipped_without_a_spill_target() -> None:
    """Nothing can be demoted with nowhere to put it; report, do not drop."""
    provider = ContextProvider(max_chars=1000, max_prompt_tokens=1)
    messages = [_tool_message(0)]

    bundle = provider.assemble([], messages)

    assert bundle.messages == messages
    assert bundle.budget.over_budget


def test_p3_references_survive_shedding() -> None:
    """A reproducible reference is the cheapest thing in the prompt and the one
    thing that makes a demotion reversible."""
    provider = ContextProvider(max_chars=10, max_prompt_tokens=1)
    artifact_id = "a" * 64

    bundle = provider.assemble(
        [
            ContextItem(
                key=f"artifact:{artifact_id}",
                text="",
                priority=Priority.P3,
                ref=_ref(artifact_id),
            )
        ],
        [],
        spill=_spiller({}),
    )

    assert artifact_id in bundle.system_context


def _ref(artifact_id: str):
    from maestro.runtime.store import ArtifactRef

    return ArtifactRef(
        artifact_id=artifact_id, sha256=artifact_id, media_type="application/json", bytes=1
    )


# ── Integration: the coordinator's side of the budget ────────────────────────

import pytest

from maestro.runtime.capabilities import CapabilityCall, CapabilityKind, CapabilitySpec
from maestro.runtime.capabilities import CapabilityRegistry
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.model import ModelAction
from maestro.runtime.models import RunStatus
from maestro.runtime.policy import PolicyGate
from maestro.runtime.store import ARTIFACT_READ_CAPABILITY, ArtifactStore, RunStore

from fakes import CountingExecutor


class ReadBackDemotedResultModel:
    """Call a bulky tool repeatedly, then read back whatever got demoted."""

    def __init__(self, calls: int) -> None:
        self.calls = calls
        self.turn = 0
        self.read_back: str = ""

    async def next_turn(self, _context, capabilities, messages=None) -> ModelAction:
        self.turn += 1
        if self.turn <= self.calls:
            # Vary the arguments: three identical calls would trip cycle detection
            # before the conversation ever grew large enough to be budgeted.
            return ModelAction(
                kind="call", call=CapabilityCall(name="dump", arguments={"page": self.turn})
            )
        demoted = [
            json.loads(message["content"])
            for message in messages or []
            if message.get("role") == "tool" and "artifact_ref" in message.get("content", "")
        ]
        if demoted and not self.read_back:
            self.read_back = demoted[0]["artifact_ref"]
            return ModelAction(
                kind="call",
                call=CapabilityCall(
                    name=ARTIFACT_READ_CAPABILITY, arguments={"artifact_id": self.read_back}
                ),
            )
        return ModelAction(kind="final", text="完成。")


@pytest.mark.asyncio
async def test_a_demoted_result_can_still_be_read_back_by_the_model(tmp_path) -> None:
    """Demotion must stay reversible end to end.

    `_artifact_call_is_owned` decides visibility from the context items, so a
    spilled result whose reference is never registered would hand the model an
    id it is then refused permission to read.
    """
    registry = CapabilityRegistry()
    model = ReadBackDemotedResultModel(calls=4)
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(
            max_chars=8_000, max_prompt_tokens=2_000, keep_recent_tool_results=1
        ),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=artifact_store,
        events=EventPublisher(JsonlJournal(tmp_path / "journal.jsonl")),
        # Keep results inline so the budget, not the per-result threshold, is
        # what demotes them.
        artifact_threshold_bytes=10_000_000,
    )
    registry.register(
        CapabilitySpec(
            name="dump",
            kind=CapabilityKind.TOOL,
            input_schema={"type": "object"},
            executor=CountingExecutor({"rows": "排产数据" * 400}),
        )
    )
    registry.register(
        CapabilitySpec(
            name=ARTIFACT_READ_CAPABILITY,
            kind=CapabilityKind.TOOL,
            input_schema={"type": "object"},
            executor=CountingExecutor({"content": "回读成功"}),
        )
    )
    coordinator.set_intent_classifier(IntentClassifier(registry.snapshot()))

    run = await coordinator.start(
        "反复取数", tool_names=["dump", ARTIFACT_READ_CAPABILITY], max_steps=12
    )

    assert model.read_back, "the budget was expected to demote at least one result"
    # Not `artifact_not_visible`: the reference the model was handed is one it
    # is allowed to dereference.
    assert run.status is RunStatus.COMPLETED
