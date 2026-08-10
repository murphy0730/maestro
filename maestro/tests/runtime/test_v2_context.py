from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.capabilities import CapabilityKind, CapabilitySpec
from maestro.runtime.checkpointing import CheckpointManager, reduce_checkpoint
from maestro.runtime.definition import AgentDefinition, SkillIndexEntry
from maestro.runtime.session_context import ContextPolicy, ModelProfile, SessionContextBuilder
from maestro.runtime.status import StatusBarBuilder
from maestro.runtime.trajectory import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentSession,
    CheckpointState,
    ConstraintState,
    FactState,
    SourceRef,
    StateDelta,
)


def make_session(definition: AgentDefinition) -> AgentSession:
    prefix, prefix_hash, index_hash = definition.freeze_prefix(
        [SkillIndexEntry(skill_id="analysis", name="Analysis", description="Analyze", version="1")]
    )
    return AgentSession(
        agent_id=definition.agent_id,
        agent_definition_version=definition.version,
        prefix_text=prefix,
        prefix_hash=prefix_hash,
        capability_index_hash=index_hash,
        model_profile_id="test",
    )


def test_prefix_is_deterministic_and_session_frozen() -> None:
    definition = AgentDefinition(
        agent_id="test",
        version="1",
        system_prompt="fixed",
        tool_namespaces={"B": "second", "A": "first"},
    )
    first = make_session(definition)
    second = make_session(definition)
    assert first.prefix_text == second.prefix_text
    assert first.prefix_hash == hashlib.sha256(first.prefix_text.encode()).hexdigest()


def test_checkpoint_reducer_applies_removal_and_supersession() -> None:
    previous = CheckpointState(
        primary_goal="goal",
        constraints=[ConstraintState(constraint_id="c1", value="old", source_ref="event://1")],
    )
    updated = reduce_checkpoint(
        previous,
        StateDelta(
            constraint_ids_removed=["c1"],
            constraints_added=[
                ConstraintState(constraint_id="c2", value="new", source_ref="event://2")
            ],
        ),
    )
    assert [item.constraint_id for item in updated.constraints] == ["c2"]


@pytest.mark.asyncio
async def test_compaction_keeps_explicit_state_and_context_uses_only_hot_events(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    definition = AgentDefinition(agent_id="test", version="1", system_prompt="fixed")
    session = store.create_session(make_session(definition))
    run = AgentRun(session_id=session.session_id, objective="finish task")
    store.create_run_with_events(
        run,
        [
            AgentEvent(
                session_id=session.session_id,
                run_id=run.run_id,
                event_type=AgentEventType.RUN_CREATED,
                payload={"objective": run.objective},
            ),
            AgentEvent(
                session_id=session.session_id,
                run_id=run.run_id,
                event_type=AgentEventType.CONSTRAINT_ADDED,
                payload={"constraint_id": "c1", "content": "must be safe"},
            ),
        ],
    )
    first_events = store.list_events(session.session_id)
    checkpoint = await CheckpointManager(store).compact(
        session.session_id, covered_until_sequence=first_events[-1].sequence
    )
    assert checkpoint is not None
    assert checkpoint.state.primary_goal == "finish task"
    assert checkpoint.state.constraints[0].value == "must be safe"

    latest = store.append_event(
        AgentEvent(
            session_id=session.session_id,
            run_id=run.run_id,
            event_type=AgentEventType.USER_MESSAGE,
            payload={"content": "latest detail"},
        )
    )
    context = SessionContextBuilder(store, StatusBarBuilder(store)).build(
        session,
        run,
        [CapabilitySpec(name="core", kind=CapabilityKind.TOOL, version="1")],
        ModelProfile(profile_id="test"),
    )
    rendered = "\n".join(str(message.get("content")) for message in context.messages)
    assert "latest detail" in rendered
    assert "must be safe" in context.messages[0]["content"]
    assert context.manifest.first_event_sequence == latest.sequence
    assert context.messages[-1]["content"].endswith("</agent_state>")


def test_status_bar_marks_expired_volatile_fact(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    definition = AgentDefinition(agent_id="test", version="1", system_prompt="fixed")
    session = store.create_session(make_session(definition))
    run = AgentRun(session_id=session.session_id, objective="goal")
    checkpoint = CheckpointState(
        primary_goal="goal",
        facts=[
            FactState(
                fact_id="f1",
                value="resource was available",
                source=SourceRef(source_type="tool", source_ref="tool-result://1"),
                validity="volatile",
                observed_at=datetime.now(UTC) - timedelta(hours=2),
                refresh_after=datetime.now(UTC) - timedelta(hours=1),
            )
        ],
    )
    status = StatusBarBuilder(store).build(run, checkpoint, [])
    assert "事实已过期" in status.blockers[0]
    assert len(status.render()) < 3200


def test_context_policy_reserves_output_and_safety_margin() -> None:
    policy = ContextPolicy.for_model(
        ModelProfile(profile_id="small", context_window=16_000, max_output_tokens=2_000)
    )
    assert policy.hard_limit == 16_000 - 2_000 - 2_048
    assert policy.compact_trigger < policy.force_compact_trigger < policy.hard_limit
