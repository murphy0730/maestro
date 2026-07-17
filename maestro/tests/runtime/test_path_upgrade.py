from __future__ import annotations

from pathlib import Path

import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec, RiskLevel
from maestro.runtime.context import ContextItem, ContextProvider
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.models import RunIntent, RunPath, RunRecord, RunStatus
from maestro.runtime.policy import PolicyGate
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.store import ArtifactStore, RunStore
from fakes import CountingExecutor, FakeRuntimeModel


class RuntimeHarness:
    def __init__(self, tmp_path: Path, *, skill_catalog: SkillCatalog | None = None) -> None:
        self.registry = CapabilityRegistry()
        self.model = FakeRuntimeModel()
        self.publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
        self.runs = RunStore(tmp_path / "runs")
        self.artifacts = ArtifactStore(tmp_path / "artifacts")
        self.coordinator = RunCoordinator(
            model=self.model,
            capabilities=self.registry,
            intent_classifier=IntentClassifier(self.registry.snapshot()),
            policy_gate=PolicyGate([]),
            context_provider=ContextProvider(max_chars=8_000),
            run_store=self.runs,
            artifact_store=self.artifacts,
            events=self.publisher,
            skill_catalog=skill_catalog,
        )

    def add(self, spec: CapabilitySpec) -> None:
        self.registry.register(spec)
        self.coordinator.set_intent_classifier(IntentClassifier(self.registry.snapshot()))


@pytest.fixture
def runtime_harness(tmp_path: Path) -> RuntimeHarness:
    return RuntimeHarness(tmp_path)


async def test_complex_request_uses_controlled_execution(runtime_harness: RuntimeHarness) -> None:
    runtime_harness.model.queue_final("受控执行完成。")
    run = await runtime_harness.coordinator.start("读取 ERP 后更新 MES")

    assert run.path is RunPath.STRUCTURED
    assert run.status is RunStatus.COMPLETED
    assert not hasattr(run, "goal_spec")
    assert not hasattr(run, "typed_plan")


async def test_fast_path_upgrades_before_high_risk_write_and_continues_controlled(
    runtime_harness: RuntimeHarness,
) -> None:
    read = CountingExecutor({"work_order": "WO-1"})
    write = CountingExecutor()
    runtime_harness.add(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=read))
    runtime_harness.add(
        CapabilitySpec(
            name="write",
            kind=CapabilityKind.TOOL,
            writes=True,
            risk=RiskLevel.HIGH,
            executor=write,
        )
    )
    runtime_harness.model.queue_call("read", {"id": "WO-1"})
    runtime_harness.model.queue_call("write", {"id": "WO-1"})
    runtime_harness.model.queue_final("已转入受控执行。")

    run = await runtime_harness.coordinator.start(
        "读取工单", tool_names=["read"], max_steps=6
    )

    assert run.status is RunStatus.COMPLETED
    assert run.path is RunPath.STRUCTURED
    assert run.consumed_steps == 1
    assert read.calls == 1
    assert write.calls == 0
    history = runtime_harness.publisher.history(run.run_id)
    upgrade_indexes = [
        index for index, event in enumerate(history) if event.type == "run.path_upgraded"
    ]
    assert len(upgrade_indexes) == 1
    upgrade = history[upgrade_indexes[0]]
    assert upgrade.data["reason"] == "high_risk_write"
    assert len(upgrade.data["artifact_working_set"]) == 1
    assert upgrade_indexes[0] < next(
        index
        for index, event in enumerate(history)
        if index > upgrade_indexes[0] and event.type == "model.turn"
    )


async def test_upgrade_persists_the_running_controlled_snapshot_before_next_turn(
    tmp_path: Path,
) -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=CountingExecutor()))
    registry.register(
        CapabilitySpec(
            name="write", kind=CapabilityKind.TOOL, writes=True, executor=CountingExecutor()
        )
    )
    runs = RunStore(tmp_path / "runs")

    class SnapshotCheckingModel(FakeRuntimeModel):
        observed_status: RunStatus | None = None

        async def next_turn(self, context, capabilities):
            if len(self.contexts) == 2:
                run_id = next(runs.directory.glob("*.json")).stem
                self.observed_status = runs.load(run_id).status
            return await super().next_turn(context, capabilities)

    model = SnapshotCheckingModel()
    model.queue_call("read")
    model.queue_call("write")
    model.queue_final("done")
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=runs,
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=EventPublisher(JsonlJournal(tmp_path / "journal.jsonl")),
    )

    await coordinator.start("读取", tool_names=["read"], max_steps=6)

    assert model.observed_status is RunStatus.RUNNING_STRUCTURED


async def test_resumed_controlled_run_rejects_a_replaced_capability_snapshot(
    tmp_path: Path,
) -> None:
    registry = CapabilityRegistry()
    original = CountingExecutor()
    replacement = CountingExecutor()
    registry.register(
        CapabilitySpec(name="read", kind=CapabilityKind.TOOL, version="1", executor=original)
    )
    runs = RunStore(tmp_path / "runs")
    coordinator = RunCoordinator(
        model=FakeRuntimeModel(),
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=runs,
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=EventPublisher(JsonlJournal(tmp_path / "journal.jsonl")),
    )
    original_snapshot = registry.snapshot()
    fast_run = RunRecord(
        objective="读取",
        path=RunPath.FAST,
        status=RunStatus.RUNNING_FAST,
        intent=RunIntent(objective="读取", candidate_capabilities=["read"], path=RunPath.FAST),
        capability_versions=original_snapshot.versions(),
    )
    upgraded = coordinator._upgrade_to_controlled_execution(
        fast_run, "high_risk_write", [ContextItem.from_run(fast_run)]
    )
    persisted = runs.load(upgraded.run_id)
    registry.register(
        CapabilitySpec(name="read", kind=CapabilityKind.TOOL, version="2", executor=replacement),
        replace=True,
    )

    resumed = await coordinator.run_until_blocked(persisted)

    assert resumed.status is RunStatus.FAILED
    assert original.calls == 0
    assert replacement.calls == 0


async def test_fork_skill_uses_isolated_limited_child_run(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    read = CountingExecutor({"order": "WO-1"})
    registry.register(CapabilitySpec(name="fork-order", kind=CapabilityKind.SKILL))
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=read))
    registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, executor=CountingExecutor()))
    skill = tmp_path / "skills" / "fork-order" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: fork-order\ndescription: fork\ncontext: fork\nallowed-tools: read\n---\n"
        "Secret child instructions $ARGUMENTS\n"
    )
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    model.queue_call("fork-order", {"arguments": "WO-1"})
    model.queue_call("read", {"id": "WO-1"})
    model.queue_final("child done")
    model.queue_final("parent done")
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    runs = RunStore(tmp_path / "runs")
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot(), skills=catalog.discover()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=runs,
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
    )

    parent = await coordinator.start(
        "委派检查", requested_skills=["fork-order"], tool_names=["read"], max_steps=8
    )

    child_created = [event for event in publisher.history(parent.run_id) if event.type == "child_run.created"]
    assert parent.status is RunStatus.COMPLETED
    assert parent.path is RunPath.STRUCTURED
    assert len(child_created) == 1
    child = runs.load(child_created[0].data["child_run_id"])
    assert child.parent_run_id == parent.run_id
    assert child.intent is not None
    assert child.intent.max_steps < parent.intent.max_steps
    assert child.intent.candidate_capabilities == ["read"]
    assert "Secret child instructions WO-1" not in model.contexts[-1].system_context
    assert "child done" not in model.contexts[-1].system_context
    assert "artifact:" in model.contexts[-1].system_context
    assert read.calls == 1


async def test_fork_rejects_a_parent_budget_that_cannot_be_reduced(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="fork-order", kind=CapabilityKind.SKILL))
    skill = tmp_path / "skills" / "fork-order" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: fork-order\ndescription: fork\ncontext: fork\n---\nfork\n")
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    model.queue_call("fork-order")
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot(), skills=catalog.discover()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
    )

    parent = await coordinator.start("委派", requested_skills=["fork-order"], max_steps=1)

    assert parent.status is RunStatus.FAILED
    assert publisher.history(parent.run_id)[-1].data["reason"] == "child_budget_not_smaller"
    assert not [event for event in publisher.history(parent.run_id) if event.type == "child_run.created"]


async def test_explicit_manual_fork_uses_isolated_child_without_model_exposure(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    read = CountingExecutor({"order": "WO-1"})
    registry.register(CapabilitySpec(name="manual-fork", kind=CapabilityKind.SKILL))
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=read))
    skill = tmp_path / "skills" / "manual-fork" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: manual-fork\ndescription: manual fork\ncontext: fork\n"
        "disable-model-invocation: true\nallowed-tools: read\n---\nsecret child work\n"
    )
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    model.queue_call("read", {"id": "WO-1"})
    model.queue_final("child done")
    model.queue_final("parent done")
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    runs = RunStore(tmp_path / "runs")
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot(), skills=catalog.discover()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=runs,
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
    )

    parent = await coordinator.start(
        "显式委派", requested_skills=["manual-fork"], tool_names=["read"], max_steps=8
    )

    created = [event for event in publisher.history(parent.run_id) if event.type == "child_run.created"]
    assert parent.status is RunStatus.COMPLETED
    assert len(created) == 1
    child = runs.load(created[0].data["child_run_id"])
    assert child.intent is not None
    assert child.intent.max_steps < parent.intent.max_steps
    assert child.intent.candidate_capabilities == ["read"]
    assert all("manual-fork" not in names for names in model.capability_names)
    assert read.calls == 1


async def test_controlled_skills_consume_the_strict_step_budget(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    for name in ("first", "second", "third"):
        registry.register(CapabilitySpec(name=name, kind=CapabilityKind.SKILL))
        skill = tmp_path / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(f"---\nname: {name}\ndescription: {name}\n---\n{name}\n")
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry.snapshot())
    catalog.discover()
    model = FakeRuntimeModel()
    for name in ("first", "second", "third"):
        model.queue_call(name)
    publisher = EventPublisher(JsonlJournal(tmp_path / "journal.jsonl"))
    coordinator = RunCoordinator(
        model=model,
        capabilities=registry,
        intent_classifier=IntentClassifier(registry.snapshot(), skills=catalog.discover()),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=8_000),
        run_store=RunStore(tmp_path / "runs"),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        events=publisher,
        skill_catalog=catalog,
    )

    run = await coordinator.start(
        "加载三个技能", requested_skills=["first", "second", "third"], max_steps=4
    )

    assert run.status is RunStatus.FAILED
    assert run.consumed_steps == 2
    assert publisher.history(run.run_id)[-1].data["reason"] == "controlled_budget_exhausted"
