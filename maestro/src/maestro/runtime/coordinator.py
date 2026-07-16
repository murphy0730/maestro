from __future__ import annotations

import json
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySnapshot,
    CapabilitySpec,
)
from maestro.runtime.context import ContextItem, ContextProvider
from maestro.runtime.events import EventPublisher, RunEvent
from maestro.runtime.intent import IntentClassifier, IntentRequest
from maestro.runtime.model import RuntimeModel
from maestro.runtime.models import RunPath, RunRecord, RunStatus
from maestro.runtime.policy import PolicyContext, PolicyEffect, PolicyGate
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.state_machine import transition_run
from maestro.runtime.store import ArtifactStore, RunStore


class RunCoordinator:
    """Own the bounded fast loop; it is the only runtime component changing Run state."""

    def __init__(
        self,
        *,
        model: RuntimeModel,
        capabilities: CapabilityRegistry,
        intent_classifier: IntentClassifier,
        policy_gate: PolicyGate,
        context_provider: ContextProvider,
        run_store: RunStore,
        artifact_store: ArtifactStore,
        events: EventPublisher,
        skill_catalog: SkillCatalog | None = None,
        artifact_threshold_bytes: int = 4096,
    ) -> None:
        self._model = model
        self._capabilities = capabilities
        self._intent_classifier = intent_classifier
        self._policy_gate = policy_gate
        self._context_provider = context_provider
        self._run_store = run_store
        self._artifact_store = artifact_store
        self._events = events
        self._skill_catalog = skill_catalog
        self._artifact_threshold_bytes = artifact_threshold_bytes

    def set_intent_classifier(self, classifier: IntentClassifier) -> None:
        """Replace the injected classifier when a host updates its capability registry."""
        self._intent_classifier = classifier

    async def start(
        self,
        objective: str,
        *,
        source: str = "chat",
        principal_id: str = "local-user",
        tool_names: list[str] | None = None,
        requested_skills: list[str] | None = None,
        max_steps: int = 12,
        max_seconds: int = 300,
    ) -> RunRecord:
        request = IntentRequest(
            message=objective,
            source=source,
            principal_id=principal_id,
            tool_names=tool_names or [],
            requested_skills=requested_skills or [],
            max_steps=max_steps,
            max_seconds=max_seconds,
        )
        intent = self._intent_classifier.build(request)
        snapshot = self._capabilities.snapshot()
        run = RunRecord(
            objective=objective,
            intent=intent,
            capability_versions=snapshot.versions(),
        )
        self._save_and_publish(run, "run.created", {"objective": objective, "run_id": run.run_id})
        if intent.path is RunPath.STRUCTURED:
            run = transition_run(run, RunStatus.STRUCTURING, "intent requires structure")
            self._save_and_publish(run, "run.path_selected", {"path": run.path.value})
            return run
        run = transition_run(run, RunStatus.RUNNING_FAST, "intent selects fast path")
        self._save_and_publish(run, "run.path_selected", {"path": run.path.value})
        return await self.run_until_blocked(run, snapshot)

    async def run_until_blocked(
        self, run: RunRecord, snapshot: CapabilitySnapshot | None = None
    ) -> RunRecord:
        if run.status is not RunStatus.RUNNING_FAST:
            return run
        snapshot = snapshot or self._capabilities.snapshot()
        assert run.intent is not None
        started_at = monotonic()
        calls_seen: dict[str, int] = {}
        context_items = [ContextItem.from_run(run)]
        parent_allowed = set(run.intent.candidate_capabilities) or None
        skill_allowed: set[str] | None = None
        while True:
            if monotonic() - started_at >= run.intent.max_seconds:
                return self._fail(run, "time_exhausted")
            capabilities = self._available(snapshot, parent_allowed, skill_allowed)
            context = self._context_provider.assemble(context_items)
            action = await self._model.next_turn(context, capabilities)
            self._publish(run, "model.turn", {"kind": action.kind})
            if action.kind == "final":
                run = transition_run(run, RunStatus.COMPLETED, "model final")
                run = run.model_copy(update={"final_text": action.text})
                self._save_and_publish(run, "run.completed", {"final_text": action.text})
                return run
            if run.consumed_steps >= run.intent.max_steps:
                return self._fail(run, "budget_exhausted")
            assert action.call is not None
            normalized = self._normalize(action.call)
            calls_seen[normalized] = calls_seen.get(normalized, 0) + 1
            if calls_seen[normalized] >= 3:
                return self._fail(run, "cycle_detected")
            try:
                spec = snapshot.require(action.call.name)
            except KeyError:
                return self._fail(run, "unknown_capability")
            if spec.kind is CapabilityKind.SKILL:
                loaded = self._load_inline_skill(spec, action.call, run)
                if loaded is None:
                    return self._upgrade_to_controlled_execution(
                        run, "skill_upgrade_required", context_items
                    )
                context_items.append(ContextItem.from_skill(loaded))
                allowed = set(loaded.metadata.allowed_tools)
                skill_allowed = allowed if parent_allowed is None else parent_allowed & allowed
                continue
            if spec.kind not in {CapabilityKind.TOOL, CapabilityKind.MCP} or spec.writes:
                return self._fail(run, "fast_path_read_only")
            if not self._arguments_match_schema(action.call.arguments, spec.input_schema):
                return self._fail(run, "schema_input")
            decision = self._policy_gate.evaluate(
                action.call,
                spec,
                PolicyContext(
                    principal_id=run.intent.principal_id,
                    run_allowed_tools=parent_allowed,
                    skill_allowed_tools=skill_allowed,
                ),
            )
            if decision.effect is not PolicyEffect.ALLOW:
                return self._fail(run, decision.effect.value)
            if spec.executor is None:
                return self._fail(run, "missing_executor")
            result = await spec.executor(action.call, None)
            run = run.model_copy(update={"consumed_steps": run.consumed_steps + 1})
            self._save_and_publish(run, "capability.completed", {"name": spec.name, "status": result.status})
            content = result.content
            encoded = json.dumps(content, ensure_ascii=False, default=str).encode()
            if len(encoded) > self._artifact_threshold_bytes:
                artifact = self._artifact_store.put(encoded, "application/json")
                context_items.append(ContextItem.from_artifact(artifact))
                self._publish(run, "artifact.created", artifact.model_dump())
            else:
                context_items.append(
                    ContextItem(
                        key=f"capability:{spec.name}",
                        text=json.dumps(content, ensure_ascii=False, default=str),
                    )
                )

    def _available(
        self,
        snapshot: CapabilitySnapshot,
        parent_allowed: set[str] | None,
        skill_allowed: set[str] | None,
    ) -> list[CapabilitySpec]:
        specs = list(snapshot.values())
        if parent_allowed is not None:
            specs = [spec for spec in specs if spec.name in parent_allowed or spec.kind is CapabilityKind.SKILL]
        if skill_allowed is not None:
            specs = [spec for spec in specs if spec.name in skill_allowed]
        return specs

    def _load_inline_skill(self, spec: CapabilitySpec, call: CapabilityCall, run: RunRecord) -> Any | None:
        if self._skill_catalog is None:
            return None
        arguments = call.arguments.get("arguments", "")
        loaded = self._skill_catalog.load(spec.name, arguments=str(arguments), session_id=run.run_id)
        if loaded.mode != "inline":
            return None
        return loaded

    @staticmethod
    def _normalize(call: CapabilityCall) -> str:
        return json.dumps({"name": call.name, "arguments": call.arguments}, sort_keys=True, ensure_ascii=False, default=str)

    @staticmethod
    def _arguments_match_schema(arguments: dict[str, object], schema: dict[str, object]) -> bool:
        if not schema or schema.get("type", "object") != "object":
            return not schema
        required = schema.get("required", [])
        return isinstance(required, list) and all(isinstance(key, str) and key in arguments for key in required)

    def _fail(self, run: RunRecord, reason: str) -> RunRecord:
        run = transition_run(run, RunStatus.FAILED, reason)
        self._save_and_publish(run, "run.failed", {"reason": reason})
        return run

    def _upgrade_to_controlled_execution(
        self, run: RunRecord, reason: str, context_items: list[ContextItem]
    ) -> RunRecord:
        """Move one fast run into controlled execution without constructing a plan."""
        artifact_working_set = [
            item.ref.model_dump()
            for item in context_items
            if item.ref is not None
        ]
        run = transition_run(run, RunStatus.STRUCTURING, reason)
        self._save_and_publish(
            run,
            "run.upgrading",
            {"reason": reason, "artifact_working_set": artifact_working_set},
        )
        run = transition_run(run, RunStatus.RUNNING_STRUCTURED, reason)
        self._save_and_publish(
            run,
            "run.upgraded",
            {"reason": reason, "artifact_working_set": artifact_working_set},
        )
        return run

    def _save_and_publish(self, run: RunRecord, event_type: str, data: dict[str, object]) -> None:
        self._run_store.save(run)
        self._publish(run, event_type, data)

    def _publish(self, run: RunRecord, event_type: str, data: dict[str, object]) -> None:
        self._events.publish(
            RunEvent(
                run_id=run.run_id,
                type=event_type,
                data=data,
                occurred_at=datetime.now(UTC),
            )
        )
