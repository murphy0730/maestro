from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySnapshot,
    CapabilitySpec,
    CapabilityResult,
    UnknownWriteOutcome,
)
from maestro.runtime.context import ContextItem, ContextProvider
from maestro.runtime.events import EventPublisher, RunEvent
from maestro.runtime.intent import IntentClassifier, IntentRequest
from maestro.runtime.model import RuntimeModel
from maestro.runtime.models import ApprovalRecord, ChildRunResult, RunPath, RunRecord, RunStatus, RuntimeErrorKind, StepRecord
from maestro.runtime.policy import PolicyContext, PolicyEffect, PolicyGate
from maestro.runtime.skills import LoadedSkill, SkillCatalog
from maestro.runtime.state_machine import transition_run
from maestro.runtime.store import ArtifactRef, ArtifactStore, RunStore


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
        session_id: str = "default",
    ) -> RunRecord:
        run = await self.create(
            objective,
            source=source,
            principal_id=principal_id,
            tool_names=tool_names,
            requested_skills=requested_skills,
            max_steps=max_steps,
            max_seconds=max_seconds,
            session_id=session_id,
        )
        return await self.execute(run.run_id)

    async def create(
        self,
        objective: str,
        *,
        source: str = "chat",
        principal_id: str = "local-user",
        tool_names: list[str] | None = None,
        requested_skills: list[str] | None = None,
        max_steps: int = 12,
        max_seconds: int = 300,
        session_id: str = "default",
    ) -> RunRecord:
        """Persist an executable Run before scheduling any model work."""
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
            session_id=session_id,
            intent=intent,
            capability_versions=snapshot.versions(),
        )
        run = self._save_and_publish(run, "run.created", {"objective": objective, "run_id": run.run_id})
        if intent.path is RunPath.STRUCTURED:
            run = transition_run(run, RunStatus.STRUCTURING, "intent requires structure")
            run = self._save_and_publish(run, "run.path_selected", {"path": run.path.value})
            run = transition_run(run, RunStatus.RUNNING_STRUCTURED, "controlled execution ready")
            run = self._save_and_publish(run, "run.controlled_started", {})
            return run
        run = transition_run(run, RunStatus.RUNNING_FAST, "intent selects fast path")
        run = self._save_and_publish(run, "run.path_selected", {"path": run.path.value})
        return run

    async def execute(self, run_id: str) -> RunRecord:
        """Continue a previously persisted Run using its pinned capability snapshot."""
        run = self._run_store.load(run_id)
        return await self.run_until_blocked(run)

    async def run_until_blocked(
        self, run: RunRecord, snapshot: CapabilitySnapshot | None = None
    ) -> RunRecord:
        if run.status is RunStatus.RUNNING_STRUCTURED:
            pinned_snapshot = self._pinned_snapshot(run, snapshot)
            if pinned_snapshot is None:
                return self._fail(run, "capability_snapshot_unavailable")
            return await self._run_controlled(run, pinned_snapshot)
        if run.status is not RunStatus.RUNNING_FAST:
            return run
        snapshot = self._pinned_snapshot(run, snapshot)
        if snapshot is None:
            return self._fail(run, "capability_snapshot_unavailable")
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
                run = self._save_and_publish(run, "run.completed", {"final_text": action.text})
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
            if spec.writes:
                upgraded = self._upgrade_to_controlled_execution(run, "high_risk_write", context_items)
                return await self._run_controlled(
                    upgraded, snapshot, context_items, parent_allowed, skill_allowed
                )
            if spec.kind is CapabilityKind.SKILL:
                loaded = self._load_inline_skill(spec, action.call, run)
                if loaded is None:
                    upgraded = self._upgrade_to_controlled_execution(
                        run, "skill_upgrade_required", context_items
                    )
                    return await self._run_controlled(
                        upgraded, snapshot, context_items, parent_allowed, skill_allowed
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
            if result.status != "succeeded":
                self._publish(run, "step.failed", {"name": spec.name, "status": result.status})
                return self._fail(run, result.error_message or "capability_failed")
            run = run.model_copy(update={"consumed_steps": run.consumed_steps + 1})
            run = self._save_and_publish(run, "capability.completed", {"name": spec.name, "status": result.status})
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

    async def _run_controlled(
        self,
        run: RunRecord,
        snapshot: CapabilitySnapshot,
        context_items: list[ContextItem] | None = None,
        parent_allowed: set[str] | None = None,
        skill_allowed: set[str] | None = None,
    ) -> RunRecord:
        """Execute sequential model actions with controlled budgets and no plan graph."""
        assert run.intent is not None
        context_items = context_items or [ContextItem.from_run(run)]
        if parent_allowed is None:
            parent_allowed = set(run.intent.candidate_capabilities) or None
        controlled_limit = max(1, run.intent.max_steps // 2)
        started_at = monotonic()
        calls_seen: dict[str, int] = {}
        while True:
            if monotonic() - started_at >= run.intent.max_seconds:
                return self._fail(run, "time_exhausted")
            if run.consumed_steps >= controlled_limit:
                return self._fail(run, "controlled_budget_exhausted")
            action = await self._model.next_turn(
                self._context_provider.assemble(context_items),
                self._available(snapshot, parent_allowed, skill_allowed),
            )
            self._publish(run, "model.turn", {"kind": action.kind})
            if action.kind == "final":
                run = transition_run(run, RunStatus.COMPLETED, "model final")
                run = run.model_copy(update={"final_text": action.text})
                run = self._save_and_publish(run, "run.completed", {"final_text": action.text})
                return run
            assert action.call is not None
            run = run.model_copy(update={"consumed_steps": run.consumed_steps + 1})
            run = self._save_and_publish(run, "run.step_consumed", {})
            normalized = self._normalize(action.call)
            calls_seen[normalized] = calls_seen.get(normalized, 0) + 1
            if calls_seen[normalized] >= 3:
                return self._fail(run, "cycle_detected")
            try:
                spec = snapshot.require(action.call.name)
            except KeyError:
                return self._fail(run, "unknown_capability")
            if spec.kind is CapabilityKind.SKILL:
                loaded = self._load_skill(spec, action.call, run)
                if loaded is None:
                    return self._fail(run, "missing_skill_catalog")
                if loaded.mode == "fork":
                    if run.intent.max_steps <= 1:
                        return self._fail(run, "child_budget_not_smaller")
                    child_result, artifact = await self._run_child(
                        run, snapshot, loaded, parent_allowed
                    )
                    context_items.append(ContextItem.from_artifact(artifact))
                    self._publish(run, "child_run.completed", child_result.model_dump())
                    continue
                if loaded.mode != "inline":
                    return self._fail(run, "unsupported_skill_context")
                context_items.append(ContextItem.from_skill(loaded))
                allowed = set(loaded.metadata.allowed_tools)
                skill_allowed = allowed if parent_allowed is None else parent_allowed & allowed
                continue
            if spec.kind not in {CapabilityKind.TOOL, CapabilityKind.MCP}:
                return self._fail(run, "unsupported_capability")
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
            if decision.effect in {PolicyEffect.REQUIRE_CONFIRMATION, PolicyEffect.REQUIRE_RECONFIRMATION}:
                return await self._request_approval(run, action.call, spec, decision, parent_allowed, skill_allowed)
            if decision.effect is not PolicyEffect.ALLOW:
                return self._fail(run, decision.effect.value)
            if spec.executor is None:
                return self._fail(run, "missing_executor")
            if spec.writes:
                return await self._execute_write(run, action.call, spec)
            result = await spec.executor(action.call, None)
            if result.status != "succeeded":
                self._publish(run, "step.failed", {"name": spec.name, "status": result.status})
                return self._fail(run, result.error_message or "capability_failed")
            run = self._save_and_publish(
                run, "capability.completed", {"name": spec.name, "status": result.status}
            )
            self._append_result_context(context_items, run, spec.name, result.content)

    async def _run_child(
        self,
        parent: RunRecord,
        snapshot: CapabilitySnapshot,
        loaded: LoadedSkill,
        parent_allowed: set[str] | None,
    ) -> tuple[ChildRunResult, ArtifactRef]:
        assert parent.intent is not None
        skill_allowed = set(loaded.metadata.allowed_tools)
        child_allowed = skill_allowed if parent_allowed is None else parent_allowed & skill_allowed
        child_intent = parent.intent.model_copy(
            update={
                "objective": loaded.metadata.description,
                "requested_skills": [],
                "candidate_capabilities": sorted(child_allowed),
                "max_steps": max(1, parent.intent.max_steps // 2),
                "path": RunPath.STRUCTURED,
            }
        )
        child = RunRecord(
            parent_run_id=parent.run_id,
            objective=child_intent.objective,
            intent=child_intent,
            capability_versions=parent.capability_versions,
        )
        child = self._save_and_publish(child, "run.created", {"objective": child.objective, "run_id": child.run_id})
        child = transition_run(child, RunStatus.STRUCTURING, "fork skill requires controlled execution")
        child = self._save_and_publish(child, "run.path_selected", {"path": child.path.value})
        child = transition_run(child, RunStatus.RUNNING_STRUCTURED, "child controlled execution ready")
        child = self._save_and_publish(child, "run.controlled_started", {})
        self._publish(parent, "child_run.created", {"child_run_id": child.run_id})
        child = await self._run_controlled(
            child,
            snapshot,
            [ContextItem.from_run(child), ContextItem.from_skill(loaded)],
            child_allowed,
            child_allowed,
        )
        artifact = self._artifact_store.put(
            json.dumps(
                {"child_run_id": child.run_id, "status": child.status.value, "final_text": child.final_text},
                ensure_ascii=False,
            ).encode(),
            "application/json",
        )
        self._publish(child, "artifact.created", artifact.model_dump())
        return (
            ChildRunResult(
                child_run_id=child.run_id,
                status=child.status,
                artifact_ref=artifact.artifact_id,
            ),
            artifact,
        )

    def _append_result_context(
        self, context_items: list[ContextItem], run: RunRecord, name: str, content: object | None
    ) -> None:
        encoded = json.dumps(content, ensure_ascii=False, default=str).encode()
        if len(encoded) > self._artifact_threshold_bytes:
            artifact = self._artifact_store.put(encoded, "application/json")
            context_items.append(ContextItem.from_artifact(artifact))
            self._publish(run, "artifact.created", artifact.model_dump())
            return
        context_items.append(
            ContextItem(key=f"capability:{name}", text=json.dumps(content, ensure_ascii=False, default=str))
        )

    def _load_skill(
        self, spec: CapabilitySpec, call: CapabilityCall, run: RunRecord
    ) -> LoadedSkill | None:
        if self._skill_catalog is None:
            return None
        return self._skill_catalog.load(
            spec.name, arguments=str(call.arguments.get("arguments", "")), session_id=run.run_id
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

    def _pinned_snapshot(
        self, run: RunRecord, snapshot: CapabilitySnapshot | None
    ) -> CapabilitySnapshot | None:
        candidate = snapshot or self._capabilities.snapshot()
        if candidate.versions() != run.capability_versions:
            return None
        return candidate

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
        return self._save_and_publish(run, "run.failed", {"reason": reason})

    async def approve(
        self, run_id: str, approval_id: str, approved: bool, principal_id: str, expected_revision: int
    ) -> RunRecord:
        async with self._run_store.lock_for(run_id):
            run = self._run_store.load(run_id)
            if run.status is not RunStatus.WAITING_APPROVAL or run.revision != expected_revision:
                raise ValueError("stale approval revision")
            approval = next((item for item in run.pending_approvals if item.approval_id == approval_id), None)
            if approval is None or approval.status != "pending" or approval.run_revision != expected_revision:
                raise ValueError("unknown or stale approval")
            if not approved:
                rejected = approval.model_copy(update={"status": "rejected"})
                run = run.model_copy(update={"pending_approvals": [rejected]})
                run = self._save_and_publish(
                    run, "approval.resolved", {"approval_id": approval_id, "approved": False}
                )
                return self._fail(run, "approval_rejected")
            step = run.steps.get(approval.step_id)
            if step is None or step.call is None:
                return self._fail(run, "approval_action_missing")
            call = CapabilityCall.model_validate(step.call)
            snapshot = self._pinned_snapshot(run, None)
            if snapshot is None:
                return self._fail(run, "capability_snapshot_unavailable")
            spec = snapshot.require(call.name)
            allowed = set(run.intent.candidate_capabilities) if run.intent and run.intent.candidate_capabilities else None
            decision = self._policy_gate.evaluate(
                call,
                spec,
                PolicyContext(
                    principal_id=principal_id,
                    run_allowed_tools=set(approval.run_allowed_tools) if approval.run_allowed_tools is not None else None,
                    skill_allowed_tools=set(approval.skill_allowed_tools) if approval.skill_allowed_tools is not None else None,
                ),
            )
            token = await self._external_state_token(spec, call)
            if (
                approval.expires_at <= datetime.now(UTC)
                or token != approval.external_state_token
                or decision.effect is not PolicyEffect.ALLOW
            ):
                expired = approval.model_copy(update={"status": "expired"})
                run = run.model_copy(update={"pending_approvals": [expired]})
                self._publish(run, "approval.expired", {"approval_id": approval_id})
                if decision.effect is PolicyEffect.DENY:
                    return self._fail(run, decision.reason)
                return await self._request_approval(run, call, spec, decision, allowed, set(approval.skill_allowed_tools) if approval.skill_allowed_tools is not None else None, replace=True)
            run = run.model_copy(update={"pending_approvals": []})
            run = transition_run(run, RunStatus.RUNNING_STRUCTURED, "approval granted")
            if not self._run_store.compare_and_save(run, expected_revision):
                raise ValueError("stale approval revision")
            self._publish(
                run,
                "approval.approved",
                {"approval_id": approval_id, "snapshot_revision": run.revision, "run_snapshot": run.model_dump(mode="json")},
            )
        return await self._execute_write(run, call, spec, step.step_id)

    async def cancel(self, run_id: str) -> RunRecord:
        async with self._run_store.lock_for(run_id):
            run = self._run_store.load(run_id)
            if run.status is RunStatus.RECONCILING or run.requires_reconciliation:
                return self._save_and_publish(run, "run.cancel_deferred", {"reason": "requires_reconciliation"})
            if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            if run.status is RunStatus.CANCELLING:
                return run
            run = transition_run(run, RunStatus.CANCELLING, "cancel requested")
            run = self._save_and_publish(run, "run.cancelling", {})
            if run.inflight_step_id is not None:
                return run
            run = transition_run(run, RunStatus.CANCELLED, "cancelled safely")
            return self._save_and_publish(run, "run.cancelled", {})

    async def reconcile(self, run_id: str) -> RunRecord:
        run = self._run_store.load(run_id)
        if run.status is not RunStatus.RECONCILING:
            return run
        step = next((item for item in run.steps.values() if item.idempotency_key and item.call), None)
        if step is None or step.call is None:
            return self._fail(run, "reconciliation_action_missing")
        snapshot = self._pinned_snapshot(run, None)
        if snapshot is None:
            return self._fail(run, "capability_snapshot_unavailable")
        spec = snapshot.require(CapabilityCall.model_validate(step.call).name)
        if spec.reconciler is None:
            return self._fail(run, "missing_reconciler")
        result = await spec.reconciler(CapabilityCall.model_validate(step.call), step.idempotency_key)
        if result.status == "unknown":
            return run
        if result.status == "failed":
            return self._fail(run, result.error_message or "reconciliation_failed")
        run = transition_run(run, RunStatus.RUNNING_STRUCTURED, "reconciled")
        run = run.model_copy(update={"requires_reconciliation": False})
        return self._save_and_publish(run, "write.reconciled", {"step_id": step.step_id})

    async def _request_approval(self, run: RunRecord, call: CapabilityCall, spec: CapabilitySpec, decision: Any, run_allowed: set[str] | None = None, skill_allowed: set[str] | None = None, replace: bool = False) -> RunRecord:
        step_id = str(uuid4())
        token = await self._external_state_token(spec, call)
        step = StepRecord(run_id=run.run_id, step_id=step_id, kind=spec.name, call=call.model_dump(), external_state_token=token)
        run = run.model_copy(update={"steps": {**run.steps, step_id: step}})
        if run.status is not RunStatus.WAITING_APPROVAL:
            run = transition_run(run, RunStatus.WAITING_APPROVAL, "approval required")
        else:
            run = run.model_copy(update={"revision": run.revision + 1, "updated_at": datetime.now(UTC)})
        approval = ApprovalRecord(run_id=run.run_id, step_id=step_id, call_sha256=self._call_sha256(call), impact_summary=f"write via {spec.name}", policy_reason=decision.reason, external_state_token=token, run_revision=run.revision, run_allowed_tools=sorted(run_allowed) if run_allowed is not None else None, skill_allowed_tools=sorted(skill_allowed) if skill_allowed is not None else None, expires_at=datetime.now(UTC) + timedelta(minutes=10))
        run = run.model_copy(update={"pending_approvals": [approval]})
        return self._save_and_publish(run, "approval.requested", {"approval_id": approval.approval_id})

    async def _execute_write(self, run: RunRecord, call: CapabilityCall, spec: CapabilitySpec, step_id: str | None = None) -> RunRecord:
        step_id = step_id or str(uuid4())
        key = str(uuid4())
        step = run.steps.get(step_id) or StepRecord(run_id=run.run_id, step_id=step_id, kind=spec.name, call=call.model_dump())
        step = step.model_copy(update={"idempotency_key": key, "call": call.model_dump()})
        run = run.model_copy(update={"steps": {**run.steps, step_id: step}, "inflight_step_id": step_id})
        run = self._save_and_publish(run, "write.started", {"step_id": step_id, "idempotency_key": key})
        try:
            result = await spec.executor(call, key) if spec.executor is not None else CapabilityResult(status="failed", error_message="missing_executor")
        except UnknownWriteOutcome:
            result = CapabilityResult(status="unknown")
        if (
            result.status == "failed"
            and spec.idempotent
            and result.error_kind is RuntimeErrorKind.TRANSIENT_INFRASTRUCTURE
            and result.error_kind in spec.retryable_errors
            and run.intent is not None
            and run.consumed_steps < max(1, run.intent.max_steps // 2)
        ):
            run = self._save_and_publish(run, "write.retrying", {"step_id": step_id})
            run, claimed = await self._claim_retry(run, step_id)
            if not claimed:
                return run
            try:
                result = await spec.executor(call, key) if spec.executor is not None else result
            except UnknownWriteOutcome:
                result = CapabilityResult(status="unknown")
        async with self._run_store.lock_for(run.run_id):
            current = self._run_store.load(run.run_id)
            if current.status is RunStatus.CANCELLED:
                return current
            if current.status is RunStatus.RECONCILING:
                return current
            run = current
        if result.status == "unknown":
            run = transition_run(run, RunStatus.RECONCILING, "unknown write outcome")
            run = run.model_copy(update={"requires_reconciliation": True, "inflight_step_id": None})
            return self._save_and_publish(run, "write.unknown", {"step_id": step_id})
        if result.status == "failed":
            self._publish(run, "step.failed", {"step_id": step_id, "status": result.status})
            return self._fail(run, result.error_message or "write_failed")
        if run.status is RunStatus.CANCELLING:
            run = run.model_copy(update={"inflight_step_id": None})
            run = transition_run(run, RunStatus.CANCELLED, "cancelled after definitive write")
            return self._save_and_publish(run, "run.cancelled", {})
        run = run.model_copy(update={"inflight_step_id": None})
        return self._save_and_publish(run, "capability.completed", {"name": spec.name, "status": result.status})

    async def _claim_retry(self, run: RunRecord, step_id: str) -> tuple[RunRecord, bool]:
        """Persist exclusive retry ownership without holding a lock during execution."""
        while True:
            async with self._run_store.lock_for(run.run_id):
                current = self._run_store.load(run.run_id)
                if current.status is RunStatus.CANCELLING:
                    cancelled = transition_run(current, RunStatus.CANCELLED, "cancelled before retry")
                    return self._save_and_publish(cancelled, "run.cancelled", {"step_id": step_id}), False
                if current.status in {
                    RunStatus.CANCELLED,
                    RunStatus.RECONCILING,
                    RunStatus.COMPLETED,
                    RunStatus.FAILED,
                }:
                    return current, False
                step = current.steps.get(step_id)
                expected_attempt = run.steps[step_id].attempt
                if step is None or step.attempt != expected_attempt:
                    return current, False
                claimed_step = step.model_copy(update={"attempt": step.attempt + 1})
                claimed = current.model_copy(
                    update={
                        "steps": {**current.steps, step_id: claimed_step},
                        "revision": current.revision + 1,
                        "updated_at": datetime.now(UTC),
                    }
                )
                if self._run_store.compare_and_save(claimed, current.revision):
                    self._publish(
                        claimed,
                        "write.retry_claimed",
                        {
                            "step_id": step_id,
                            "snapshot_revision": claimed.revision,
                            "run_snapshot": claimed.model_dump(mode="json"),
                        },
                    )
                    return claimed, True

    async def _external_state_token(self, spec: CapabilitySpec, call: CapabilityCall) -> str | None:
        return await spec.revalidator(call) if spec.revalidator is not None else None

    @staticmethod
    def _call_sha256(call: CapabilityCall) -> str:
        import hashlib
        return hashlib.sha256(RunCoordinator._normalize(call).encode()).hexdigest()

    def _upgrade_to_controlled_execution(
        self, run: RunRecord, reason: str, context_items: list[ContextItem]
    ) -> RunRecord:
        """Move one fast run into controlled execution without constructing a plan."""
        frozen_working_set = [
            {
                "key": item.key,
                "text": item.text,
                "artifact": item.ref.model_dump() if item.ref is not None else None,
            }
            for item in context_items
        ]
        artifact = self._artifact_store.put(
            json.dumps(frozen_working_set, ensure_ascii=False).encode(), "application/json"
        )
        artifact_working_set = [artifact.model_dump()]
        context_items.append(ContextItem.from_artifact(artifact))
        run = transition_run(run, RunStatus.STRUCTURING, reason)
        run = self._save_and_publish(
            run,
            "run.path_upgraded",
            {"reason": reason, "artifact_working_set": artifact_working_set},
        )
        run = transition_run(run, RunStatus.RUNNING_STRUCTURED, reason)
        run = self._save_and_publish(run, "run.controlled_started", {})
        return run

    def _save_and_publish(self, run: RunRecord, event_type: str, data: dict[str, object]) -> RunRecord:
        """Persist one monotonic snapshot; never replace a newer Run with a stale copy."""
        while True:
            try:
                current = self._run_store.load(run.run_id)
            except FileNotFoundError:
                candidate = run
                expected_revision = -1
            else:
                if run.revision < current.revision:
                    candidate = self._retry_stale_write(current, run, event_type)
                    if candidate is None:
                        return current
                    expected_revision = current.revision
                else:
                    expected_revision = current.revision
                    candidate = run if run.revision == current.revision + 1 else run.model_copy(
                        update={"revision": current.revision + 1, "updated_at": datetime.now(UTC)}
                    )
            if self._run_store.compare_and_save(candidate, expected_revision):
                run = candidate
                break
        self._publish(
            run,
            event_type,
            {
                **data,
                "snapshot_revision": run.revision,
                "run_snapshot": run.model_dump(mode="json"),
            },
        )
        return run

    @staticmethod
    def _retry_stale_write(current: RunRecord, _requested: RunRecord, event_type: str) -> RunRecord | None:
        """Reapply only terminal safety transitions to the freshly loaded snapshot."""
        if event_type == "write.unknown":
            target = RunStatus.RECONCILING
            update = {"requires_reconciliation": True, "inflight_step_id": None}
        elif event_type in {"run.cancelled", "capability.completed"} and current.status is RunStatus.CANCELLING:
            target = RunStatus.CANCELLED
            update = {"inflight_step_id": None}
        elif event_type == "run.cancelling":
            target = RunStatus.CANCELLING
            update = {}
        elif event_type == "run.failed":
            target = RunStatus.FAILED
            update = {}
        else:
            return None
        if current.status is target:
            return current
        try:
            return transition_run(current, target, event_type).model_copy(update=update)
        except ValueError:
            return None

    def _publish(self, run: RunRecord, event_type: str, data: dict[str, object]) -> None:
        self._events.publish(
            RunEvent(
                run_id=run.run_id,
                type=event_type,
                data=data,
                occurred_at=datetime.now(UTC),
            )
        )
