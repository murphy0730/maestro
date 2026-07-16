from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec
from maestro.runtime.context import ContextProvider
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.models import ApprovalRecord, RunIntent, RunPath, RunRecord, RunStatus
from maestro.runtime.policy import PolicyGate
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.store import ArtifactStore, RunStore
from fakes import CountingExecutor, FakeRuntimeModel, RecordingEvents


class RuntimeHarness:
    def __init__(self, tmp_path: Path) -> None:
        self.registry = CapabilityRegistry()
        self.model = FakeRuntimeModel()
        self.events = RecordingEvents()
        self.executors: dict[str, CountingExecutor] = {}
        self.publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
        self.publisher.subscribe(self.events)
        self.coordinator = RunCoordinator(
            model=self.model,
            capabilities=self.registry,
            intent_classifier=IntentClassifier(self.registry.snapshot()),
            policy_gate=PolicyGate([]),
            context_provider=ContextProvider(max_chars=8_000),
            run_store=RunStore(tmp_path / "runs"),
            artifact_store=ArtifactStore(tmp_path / "artifacts"),
            events=self.publisher,
        )

    def add_tool(self, name: str, *, executor: CountingExecutor | None = None) -> CountingExecutor:
        executor = executor or CountingExecutor()
        self.executors[name] = executor
        self.registry.register(
            CapabilitySpec(
                name=name,
                kind=CapabilityKind.TOOL,
                input_schema={"type": "object"},
                executor=executor,
            )
        )
        self.coordinator.set_intent_classifier(IntentClassifier(self.registry.snapshot()))
        return executor


@pytest.fixture
def runtime_harness(tmp_path: Path) -> RuntimeHarness:
    return RuntimeHarness(tmp_path)


async def test_simple_answer_stays_fast(runtime_harness: RuntimeHarness) -> None:
    runtime_harness.model.queue_final("OEE 是设备综合效率。")

    run = await runtime_harness.coordinator.start("解释 OEE")

    assert run.path is RunPath.FAST
    assert "goal_spec" not in type(run).model_fields
    assert "typed_plan" not in type(run).model_fields
    assert run.status is RunStatus.COMPLETED
    assert runtime_harness.events.types == [
        "run.created", "run.path_selected", "model.turn", "run.completed"
    ]


async def test_fast_loop_fails_when_step_budget_is_exhausted(runtime_harness: RuntimeHarness) -> None:
    executor = runtime_harness.add_tool("lookup")
    for _ in range(3):
        runtime_harness.model.queue_call("lookup", {"query": "OEE"})

    run = await runtime_harness.coordinator.start("查询", tool_names=["lookup"], max_steps=2)

    assert run.status is RunStatus.FAILED
    assert runtime_harness.events.types[-1] == "run.failed"
    assert runtime_harness.publisher.history(run.run_id)[-1].data["reason"] == "budget_exhausted"
    assert executor.calls == 2


async def test_fast_loop_blocks_third_identical_call_before_execution(
    runtime_harness: RuntimeHarness,
) -> None:
    executor = runtime_harness.add_tool("lookup")
    runtime_harness.model.queue_call("lookup", {"b": 2, "a": 1})
    runtime_harness.model.queue_call("lookup", {"a": 1, "b": 2})
    runtime_harness.model.queue_call("lookup", {"b": 2, "a": 1})

    run = await runtime_harness.coordinator.start("查询", tool_names=["lookup"])

    assert run.status is RunStatus.FAILED
    assert runtime_harness.publisher.history(run.run_id)[-1].data["reason"] == "cycle_detected"
    assert executor.calls == 2


async def test_inline_skill_expands_context_and_narrows_tools(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    read = CountingExecutor()
    write = CountingExecutor()
    registry.register(CapabilitySpec(name="inspect", kind=CapabilityKind.SKILL))
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=read))
    registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, executor=write))
    skill = tmp_path / "skills" / "inspect" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: inspect\ndescription: inspect\nallowed-tools: read\n---\nExpanded prompt $ARGUMENTS\n")
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    model.queue_call("inspect", {"arguments": "WO-1"})
    model.queue_final("done")
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
    )

    run = await coordinator.start("inspect", tool_names=["read"])

    assert run.status is RunStatus.COMPLETED
    assert catalog.io_log == ["inspect/SKILL.md:frontmatter", "inspect/SKILL.md:full"]
    assert "Expanded prompt WO-1" in model.contexts[1].system_context
    assert model.capability_names[1] == ["read"]
    assert read.calls == 0
    assert write.calls == 0


async def test_fast_run_upgrades_to_controlled_execution_without_typed_plan(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    lookup = CountingExecutor({"payload": "x" * 128})
    registry.register(CapabilitySpec(name="inspect", kind=CapabilityKind.SKILL))
    registry.register(CapabilitySpec(name="lookup", kind=CapabilityKind.TOOL, executor=lookup))
    skill = tmp_path / "skills" / "inspect" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: inspect\ndescription: inspect\ncontext: fork\n---\nInspect $ARGUMENTS\n")
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    model.queue_call("lookup", {"query": "WO-1"})
    model.queue_call("inspect", {"arguments": "WO-1"})
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
        artifact_threshold_bytes=1,
    )

    snapshot = registry.snapshot()
    approval = ApprovalRecord(
        run_id="run-upgrade",
        step_id="approve-write",
        call_sha256="a" * 64,
        impact_summary="already approved",
        policy_reason="policy",
        run_revision=4,
        status="approved",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    run = RunRecord(
        run_id="run-upgrade",
        objective="检查工单",
        path=RunPath.FAST,
        status=RunStatus.RUNNING_FAST,
        intent=RunIntent(
            objective="检查工单", candidate_capabilities=["lookup"], path=RunPath.FAST
        ),
        capability_versions=snapshot.versions(),
        consumed_steps=4,
        pending_approvals=[approval],
    )

    run = await coordinator.run_until_blocked(run, snapshot)

    assert run.status is RunStatus.RUNNING_STRUCTURED
    assert run.path is RunPath.STRUCTURED
    assert run.run_id == "run-upgrade"
    assert run.consumed_steps == 5
    assert run.pending_approvals == [approval]
    assert run.capability_versions == snapshot.versions()
    assert "goal_spec" not in type(run).model_fields
    assert "typed_plan" not in type(run).model_fields
    assert RunStore(tmp_path / "runs").load(run.run_id) == run
    history = publisher.history(run.run_id)
    assert [event.type for event in history][-2:] == ["run.upgrading", "run.upgraded"]
    assert history[-2].data["reason"] == "skill_upgrade_required"
    assert history[-2].data["artifact_working_set"] == history[-1].data["artifact_working_set"]
    assert history[-2].data["artifact_working_set"][0]["media_type"] == "application/json"
