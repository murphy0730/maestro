from __future__ import annotations

import json

import pytest

from maestro.extensions.retrieval import register_local_retrieval_capabilities
from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.agent import AgentRuntime
from maestro.runtime.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.checkpointing import CheckpointManager
from maestro.runtime.definition import GENERIC_AGENT_DEFINITION
from maestro.runtime.meta_tools import register_runtime_meta_capabilities
from maestro.runtime.models import RunStatus
from maestro.runtime.plan_manager import PlanManager
from maestro.runtime.policy import PolicyGate
from maestro.runtime.resolver import CapabilityResolver
from maestro.runtime.session_context import ModelProfile, SessionContextBuilder
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.status import StatusBarBuilder
from maestro.runtime.trajectory import AgentEventType

from fakes import CountingExecutor, FakeRuntimeModel


def make_runtime(
    tmp_path, model: FakeRuntimeModel, *specs: CapabilitySpec, skill_root=None
) -> tuple[AgentRuntime, SQLiteStore]:
    store = SQLiteStore(tmp_path / "runtime.db")
    registry = CapabilityRegistry()
    register_runtime_meta_capabilities(registry)
    for spec in specs:
        registry.register(spec)
    resolver = CapabilityResolver(registry, store)
    resolver.sync_index()
    skill_catalog = (
        SkillCatalog({"user": skill_root}, registry) if skill_root is not None else None
    )
    runtime = AgentRuntime(
        store=store,
        model=model,
        model_profile=ModelProfile(profile_id="test", context_window=16_000),
        definition=GENERIC_AGENT_DEFINITION,
        capabilities=registry,
        policy_gate=PolicyGate([]),
        context_builder=SessionContextBuilder(store, StatusBarBuilder(store)),
        checkpoint_manager=CheckpointManager(store),
        plan_manager=PlanManager(store),
        resolver=resolver,
        skill_catalog=skill_catalog,
    )
    return runtime, store


@pytest.mark.asyncio
async def test_agent_discovers_lazy_tool_and_completes_with_durable_events(tmp_path) -> None:
    model = FakeRuntimeModel()
    executor = CountingExecutor({"widget": "A", "quantity": 3})
    runtime, store = make_runtime(
        tmp_path,
        model,
        CapabilitySpec(
            name="query_widget",
            kind=CapabilityKind.TOOL,
            description="read widget inventory quantity",
            input_schema={"type": "object", "properties": {}},
            version="1",
            executor=executor,
        ),
    )
    model.queue_call("tool_search", {"query": "widget inventory"}, tool_call_id="search")
    model.queue_call("query_widget", {}, tool_call_id="query")
    model.queue_final("There are 3 widgets.")

    session = runtime.create_session()
    run = await runtime.create_run(session.session_id, "How many widgets are available?")
    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    assert completed.final_text == "There are 3 widgets."
    assert executor.calls == 1
    assert "query_widget" not in model.capability_names[0]
    assert "query_widget" in model.capability_names[1]
    events = store.list_events(session.session_id, run_id=run.run_id)
    assert AgentEventType.TOOL_SEARCH in {event.event_type for event in events}
    assert [event.payload["content"] for event in events if event.event_type is AgentEventType.ASSISTANT_MESSAGE] == [
        "There are 3 widgets."
    ]


@pytest.mark.asyncio
async def test_high_risk_write_waits_for_revision_bound_approval(tmp_path) -> None:
    model = FakeRuntimeModel()
    executor = CountingExecutor({"published": True})
    runtime, store = make_runtime(
        tmp_path,
        model,
        CapabilitySpec(
            name="publish_result",
            kind=CapabilityKind.TOOL,
            description="publish a result",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            risk=RiskLevel.HIGH,
            writes=True,
            version="7",
            executor=executor,
        ),
    )
    model.queue_call("tool_search", {"query": "publish result"}, tool_call_id="search")
    model.queue_call("publish_result", {"name": "v2"}, tool_call_id="write")
    model.queue_final("Published.")

    session = runtime.create_session()
    run = await runtime.create_run(session.session_id, "Publish the result")
    waiting = await runtime.execute(run.run_id)

    assert waiting.status is RunStatus.WAITING_APPROVAL
    assert executor.calls == 0
    assert waiting.pending_approval_id is not None
    completed = await runtime.resolve_approval(
        run.run_id,
        waiting.pending_approval_id,
        approved=True,
        principal_id="local-user",
        expected_revision=waiting.revision,
    )
    assert completed.status is RunStatus.COMPLETED
    assert executor.calls == 1
    events = store.list_events(session.session_id, run_id=run.run_id)
    result = next(
        event
        for event in events
        if event.event_type is AgentEventType.TOOL_RESULT
        and event.payload.get("tool_id") == "publish_result"
    )
    assert result.references["call_id"] == "write"


@pytest.mark.asyncio
async def test_runtime_attaches_principal_only_at_capability_execution(tmp_path) -> None:
    seen: list[str | None] = []

    async def execute(call, _key) -> CapabilityResult:
        seen.append(call.principal_id)
        assert "principal_id" not in call.model_dump()
        return CapabilityResult(status="succeeded", content={"ok": True})

    model = FakeRuntimeModel()
    runtime, _store = make_runtime(
        tmp_path,
        model,
        CapabilitySpec(
            name="principal_reader",
            kind=CapabilityKind.TOOL,
            description="read for one principal",
            executor=execute,
        ),
    )
    model.queue_call("tool_search", {"query": "principal reader"})
    model.queue_call("principal_reader", {})
    model.queue_final("done")
    session = runtime.create_session()
    run = await runtime.create_run(
        session.session_id,
        "read my data",
        principal_id="agent-user-a",
    )

    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    assert seen == ["agent-user-a"]


@pytest.mark.asyncio
async def test_retrieval_keeps_provider_tool_protocol_and_records_evidence(tmp_path) -> None:
    model = FakeRuntimeModel()
    runtime, store = make_runtime(tmp_path, model)
    register_local_retrieval_capabilities(runtime._capabilities, store)
    runtime._resolver.sync_index()
    store.add_knowledge_document(
        title="guide", content="Machine M03 can finish product X."
    )
    model.queue_call("knowledge_search", {"query": "Machine M03"}, tool_call_id="rag")
    model.queue_final("M03 can finish product X.")

    session = runtime.create_session()
    run = await runtime.create_run(session.session_id, "Can M03 finish product X?")
    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    events = store.list_events(session.session_id, run_id=run.run_id)
    assert AgentEventType.TOOL_RESULT in {event.event_type for event in events}
    assert AgentEventType.EVIDENCE_RECALLED in {event.event_type for event in events}
    second_turn = model.messages[1]
    assert any(
        message.get("role") == "tool" and message.get("tool_call_id") == "rag"
        for message in second_turn
    )


@pytest.mark.asyncio
async def test_explicit_skill_is_versioned_and_rehydrated_without_copying_body_into_run(
    tmp_path,
) -> None:
    skills = tmp_path / "skills"
    package = skills / "inspect" / "SKILL.md"
    package.parent.mkdir(parents=True)
    package.write_text(
        "---\nname: inspect\ndescription: inspect safely\nallowed-tools: [read_widget]\n---\n"
        "Inspect $ARGUMENTS for session ${CLAUDE_SESSION_ID}.\n",
        "utf-8",
    )
    model = FakeRuntimeModel()
    runtime, store = make_runtime(
        tmp_path,
        model,
        CapabilitySpec(
            name="read_widget",
            kind=CapabilityKind.TOOL,
            description="read widget",
            version="1",
        ),
        skill_root=skills,
    )
    model.queue_final("inspected")

    session = runtime.create_session()
    run = await runtime.create_run(
        session.session_id, "inspect widget", requested_skills=["inspect"]
    )
    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    assert "skill_prompts" not in completed.working_state
    version = completed.active_skill_versions["inspect"]
    assert "$ARGUMENTS" in store.get_skill_definition("inspect", version)["body"]
    assert any(
        "skill-guidance" in str(message.get("content"))
        for message in model.messages[0]
    )


@pytest.mark.asyncio
async def test_skill_allowlist_hides_eager_read_capabilities(tmp_path) -> None:
    skills = tmp_path / "skills"
    package = skills / "inspect" / "SKILL.md"
    package.parent.mkdir(parents=True)
    package.write_text(
        "---\nname: inspect\ndescription: inspect safely\n"
        "allowed-tools: [read_widget]\n---\nInspect the widget.\n",
        "utf-8",
    )
    model = FakeRuntimeModel()
    runtime, store = make_runtime(
        tmp_path,
        model,
        CapabilitySpec(
            name="read_widget",
            kind=CapabilityKind.TOOL,
            description="read widget",
            version="1",
        ),
        skill_root=skills,
    )
    register_local_retrieval_capabilities(runtime._capabilities, store)
    runtime._resolver.sync_index()
    model.queue_final("done")

    session = runtime.create_session()
    run = await runtime.create_run(
        session.session_id, "inspect widget", requested_skills=["inspect"]
    )
    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    assert "tool_search" in model.capability_names[0]
    assert "get_result_detail" in model.capability_names[0]
    assert "knowledge_search" not in model.capability_names[0]
    assert "memory_search" not in model.capability_names[0]


@pytest.mark.asyncio
async def test_result_detail_pages_original_result_without_recursive_reference(tmp_path) -> None:
    model = FakeRuntimeModel()
    runtime, store = make_runtime(tmp_path, model)
    session = runtime.create_session()
    run = await runtime.create_run(session.session_id, "read prior result")
    source_id = store.put_tool_result(
        session_id=session.session_id,
        run_id=run.run_id,
        tool_id="large_reader",
        tool_version="1",
        status="succeeded",
        digest={"summary": "large result"},
        raw_payload={"items": ["x" * 400, "y" * 400]},
    )
    model.queue_call(
        "get_result_detail",
        {"result_id": f"tool-result://{source_id}", "max_chars": 256},
        tool_call_id="detail",
    )
    model.queue_final("read")

    completed = await runtime.execute(run.run_id)

    assert completed.status is RunStatus.COMPLETED
    detail = next(
        event
        for event in store.list_events(session.session_id, run_id=run.run_id)
        if event.event_type is AgentEventType.TOOL_RESULT
        and event.payload.get("tool_id") == "get_result_detail"
    )
    assert detail.payload["result_ref"] == f"tool-result://{source_id}"
    assert detail.payload["digest"]["source_result_id"] == source_id
    assert detail.payload["digest"]["next_offset"] == 256
    assert detail.payload["digest"]["truncated"] is True
    tool_message = next(
        message
        for message in model.messages[1]
        if message.get("role") == "tool" and message.get("tool_call_id") == "detail"
    )
    assert json.loads(tool_message["content"])["result_ref"] == f"tool-result://{source_id}"


@pytest.mark.asyncio
async def test_final_answer_cannot_claim_unknown_evidence(tmp_path) -> None:
    model = FakeRuntimeModel()
    runtime, _store = make_runtime(tmp_path, model)
    model.queue_final(
        '{"answer":"claimed","evidence_usage":[{"evidence_id":"missing",'
        '"derived_fact":"unverified"}],"state_delta":{}}'
    )
    session = runtime.create_session()
    run = await runtime.create_run(session.session_id, "answer")

    failed = await runtime.execute(run.run_id)

    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "unknown_evidence:missing"
