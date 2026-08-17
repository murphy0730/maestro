from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from maestro.foundation.sqlite_store import SQLiteStore, SessionBusy
from maestro.runtime.models import RunStatus
from maestro.runtime.trajectory import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentSession,
    CheckpointRecord,
    CheckpointState,
    PlanRecord,
    PlanTaskRecord,
)


def session() -> AgentSession:
    prefix = "frozen"
    return AgentSession(
        agent_id="test-agent",
        agent_definition_version="1",
        prefix_text=prefix,
        prefix_hash=hashlib.sha256(prefix.encode()).hexdigest(),
        capability_index_hash="capabilities",
        model_profile_id="test-model",
    )


def test_event_sequence_is_session_scoped_and_messages_are_redacted(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    current = store.create_session(session())
    user = store.append_event(
        AgentEvent(
            session_id=current.session_id,
            event_type=AgentEventType.USER_MESSAGE,
            payload={"content": "hello"},
        )
    )
    assistant = store.append_event(
        AgentEvent(
            session_id=current.session_id,
            event_type=AgentEventType.ASSISTANT_MESSAGE,
            payload={"content": "hi"},
        )
    )

    assert (user.sequence, assistant.sequence) == (1, 2)
    assert store.redact_message(current.session_id, user.event_id, cascade=True) == [
        user.event_id,
        assistant.event_id,
    ]
    assert store.message_events(current.session_id) == []
    assert [event.sequence for event in store.list_events(current.session_id)] == [1, 2, 3]


def test_run_projection_and_creation_events_commit_together(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    current = store.create_session(session())
    run = AgentRun(session_id=current.session_id, objective="do work")
    created = AgentEvent(
        session_id=current.session_id,
        run_id=run.run_id,
        event_type=AgentEventType.RUN_CREATED,
        payload={"objective": run.objective},
    )

    saved, events = store.create_run_with_events(run, [created])
    assert store.get_session(current.session_id).active_run_id == run.run_id
    assert store.get_run(run.run_id) == saved
    assert events[0].sequence == 1

    with pytest.raises(SessionBusy):
        store.create_run_with_events(
            AgentRun(session_id=current.session_id, objective="second"), []
        )

    completed = saved.model_copy(update={"status": RunStatus.COMPLETED, "final_text": "done"})
    completed, _ = store.save_run_with_events(
        completed,
        [
            AgentEvent(
                session_id=current.session_id,
                run_id=run.run_id,
                event_type=AgentEventType.RUN_STATUS_CHANGED,
                payload={"status": "completed"},
            )
        ],
        expected_revision=0,
    )
    assert completed.revision == 1
    assert store.get_session(current.session_id).active_run_id is None


def test_checkpoint_lineage_and_plan_cycle_validation(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    current = store.create_session(session())
    first = store.save_checkpoint(
        CheckpointRecord(
            session_id=current.session_id,
            generation=1,
            covered_until_sequence=5,
            state=CheckpointState(primary_goal="goal"),
            build_type="incremental",
        )
    )
    second = store.save_checkpoint(
        CheckpointRecord(
            session_id=current.session_id,
            parent_checkpoint_id=first.checkpoint_id,
            generation=2,
            covered_until_sequence=9,
            state=CheckpointState(primary_goal="goal"),
            build_type="force",
        )
    )
    assert store.latest_checkpoint(current.session_id) == second

    run = AgentRun(session_id=current.session_id, objective="goal")
    store.create_run_with_events(run, [])
    plan = PlanRecord(session_id=current.session_id, run_id=run.run_id, goal="goal")
    one = PlanTaskRecord(plan_id=plan.plan_id, task_id="one", title="one", sequence=0)
    two = PlanTaskRecord(
        plan_id=plan.plan_id, task_id="two", title="two", sequence=1, depends_on=["one"]
    )
    store.create_plan(plan, [one, two])
    assert [task.task_id for task in store.get_plan(plan.plan_id)[1]] == ["one", "two"]

    cycle = PlanRecord(session_id=current.session_id, run_id=run.run_id, goal="cycle")
    with pytest.raises(ValueError, match="cycle"):
        store.create_plan(
            cycle,
            [
                PlanTaskRecord(
                    plan_id=cycle.plan_id,
                    task_id="a",
                    title="a",
                    sequence=0,
                    depends_on=["b"],
                ),
                PlanTaskRecord(
                    plan_id=cycle.plan_id,
                    task_id="b",
                    title="b",
                    sequence=1,
                    depends_on=["a"],
                ),
            ],
        )


def test_fts_tool_knowledge_and_memory_search(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    store.sync_tool_definition(
        tool_id="inventory",
        version="1",
        name="query_inventory",
        description="query material inventory and shortages",
        namespace="WMS",
        input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
    )
    assert store.search_tools("inventory", namespace="WMS")[0]["tool_id"] == "inventory"

    document_id = store.add_knowledge_document(
        title="process guide", content="Product X supports machine M03 for the finishing process."
    )
    recall = store.search_knowledge("machine M03")
    assert recall[0]["document_id"] == document_id

    memory_id = store.add_memory(content="Prefer urgent orders when priorities are otherwise equal")
    assert store.search_memories("urgent orders")[0]["memory_id"] == memory_id


def test_volatile_fact_requires_timestamp() -> None:
    from maestro.runtime.trajectory import FactState, SourceRef

    with pytest.raises(ValueError, match="observed_at"):
        FactState(
            fact_id="f1",
            value="machine is idle",
            source=SourceRef(source_type="tool", source_ref="tool-result://r1"),
            validity="volatile",
        )
    fact = FactState(
        fact_id="f1",
        value="machine is idle",
        source=SourceRef(source_type="tool", source_ref="tool-result://r1"),
        validity="volatile",
        observed_at=datetime.now(UTC),
    )
    assert fact.observed_at is not None
