from __future__ import annotations

import hashlib

import pytest

from maestro.extensions.retrieval import register_local_retrieval_capabilities
from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
)
from maestro.runtime.plan_manager import PlanManager
from maestro.runtime.resolver import CapabilityResolver
from maestro.runtime.trajectory import AgentRun, AgentSession, PlanTaskStatus


def create_session(store: SQLiteStore) -> AgentSession:
    session = AgentSession(
        agent_id="test",
        agent_definition_version="1",
        prefix_text="prefix",
        prefix_hash=hashlib.sha256(b"prefix").hexdigest(),
        capability_index_hash="index",
        model_profile_id="model",
    )
    return store.create_session(session)


def test_capability_search_loads_only_candidates_and_pins_version(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="query_inventory",
            kind=CapabilityKind.TOOL,
            description="query current material inventory",
            version="1",
        )
    )
    registry.register(
        CapabilitySpec(
            name="publish_schedule",
            kind=CapabilityKind.TOOL,
            description="publish a schedule",
            version="2",
        )
    )
    resolver = CapabilityResolver(registry, store)
    resolver.sync_index()
    candidates = resolver.search("material inventory").candidates
    assert [item["tool_id"] for item in candidates] == ["query_inventory"]
    assert [item.name for item in resolver.resolve({"query_inventory": "1"})] == [
        "query_inventory"
    ]

    registry.register(
        CapabilitySpec(
            name="query_inventory",
            kind=CapabilityKind.TOOL,
            description="new version",
            version="2",
        ),
        replace=True,
    )
    with pytest.raises(ValueError, match="capability_version_unavailable"):
        resolver.resolve({"query_inventory": "1"})


def test_mcp_namespace_alias_and_skill_allowlist_filter_search(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="mcp__planning__get_overview",
            kind=CapabilityKind.MCP,
            description="planning overview and solution list",
            version="1",
        )
    )
    registry.register(
        CapabilitySpec(
            name="mcp__planning__publish_schedule",
            kind=CapabilityKind.MCP,
            description="planning publish schedule",
            version="1",
        )
    )
    registry.register(
        CapabilitySpec(
            name="local_planning_helper",
            kind=CapabilityKind.TOOL,
            description="planning overview helper",
            version="1",
        )
    )
    resolver = CapabilityResolver(registry, store)
    resolver.sync_index()

    result = resolver.search(
        "planning overview publish",
        namespace="MCP",
        allowed={"mcp__planning__get_overview"},
        top_k=10,
    )

    assert result.namespace == "MCP"
    assert [candidate["tool_id"] for candidate in result.candidates] == [
        "mcp__planning__get_overview"
    ]


@pytest.mark.asyncio
async def test_local_retrieval_capabilities_are_read_only_and_bounded(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    store.add_knowledge_document(title="guide", content="Machine M03 supports product X finishing.")
    store.add_memory(content="Prefer urgent orders when priorities are equal")
    registry = CapabilityRegistry()
    register_local_retrieval_capabilities(registry, store)

    knowledge = registry.require("knowledge_search")
    assert knowledge.writes is False
    result = await knowledge.executor(
        CapabilityCall(name=knowledge.name, arguments={"query": "Machine M03"}), None
    )
    assert result.status == "succeeded"
    assert result.content["items"][0]["title"] == "guide"

    memory = registry.require("memory_search")
    result = await memory.executor(
        CapabilityCall(name=memory.name, arguments={"query": "urgent orders"}), None
    )
    assert result.content["items"][0]["content"].startswith("Prefer urgent")


def test_plan_manager_advances_only_after_dependencies(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "runtime.db")
    session = create_session(store)
    run = AgentRun(session_id=session.session_id, objective="objective")
    store.create_run_with_events(run, [])
    manager = PlanManager(store)
    plan, tasks = manager.create_default(run)
    first = manager.start(tasks[0])
    assert first.status is PlanTaskStatus.IN_PROGRESS
    completed, following = manager.complete(first)
    assert completed.status is PlanTaskStatus.COMPLETED
    assert following is not None and following.status is PlanTaskStatus.READY
