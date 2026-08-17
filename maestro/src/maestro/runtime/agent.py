"""Event-driven v2 agent runtime.

``AgentRuntime`` is the sole owner of Run lifecycle changes.  Collaborators
produce context, policy decisions, plans and durable projections, but never
advance a Run independently.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    UnknownWriteOutcome,
)
from maestro.runtime.checkpointing import CheckpointManager
from maestro.runtime.context import BudgetReport, ContextBundle
from maestro.runtime.definition import AgentDefinition, SkillIndexEntry
from maestro.runtime.intent import IntentClassifier, IntentRequest
from maestro.runtime.model import ModelAction, RuntimeModel
from maestro.runtime.models import RunPath, RunStatus, RuntimeErrorKind
from maestro.runtime.plan_manager import PlanManager
from maestro.runtime.policy import PolicyContext, PolicyEffect, PolicyGate
from maestro.runtime.resolver import CORE_CAPABILITIES, CapabilityResolver
from maestro.runtime.session_context import (
    ContextPolicy,
    ModelProfile,
    SessionContext,
    SessionContextBuilder,
)
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.state_machine import RUN_TRANSITIONS
from maestro.runtime.trajectory import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentSession,
    ApprovalState,
    EvidenceRecord,
    EvidenceUsage,
    StateDelta,
)


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class EvidenceUsageInput(BaseModel):
    evidence_id: str
    derived_fact: str
    usage_type: Literal["answer", "decision", "constraint", "tool_call", "state_update"] = (
        "answer"
    )
    future_relevant: bool = False


class TurnEnvelope(BaseModel):
    answer: str
    evidence_usage: list[EvidenceUsageInput] = Field(default_factory=list)
    state_delta: StateDelta = Field(default_factory=StateDelta)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[AgentEvent], None]] = []

    def subscribe(self, subscriber: Callable[[AgentEvent], None]) -> Callable[[], None]:
        self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(subscriber)
            except ValueError:
                pass

        return unsubscribe

    def publish(self, events: list[AgentEvent]) -> None:
        for event in events:
            for subscriber in tuple(self._subscribers):
                subscriber(event)


class AgentRuntime:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        model: RuntimeModel,
        model_profile: ModelProfile,
        definition: AgentDefinition,
        capabilities: CapabilityRegistry,
        policy_gate: PolicyGate,
        context_builder: SessionContextBuilder,
        checkpoint_manager: CheckpointManager,
        plan_manager: PlanManager,
        resolver: CapabilityResolver,
        skill_catalog: SkillCatalog | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.store = store
        self._model = model
        self._model_profile = model_profile
        self._definition = definition
        self._capabilities = capabilities
        self._policy_gate = policy_gate
        self._context_builder = context_builder
        self._checkpoint_manager = checkpoint_manager
        self._plan_manager = plan_manager
        self._resolver = resolver
        self._skill_catalog = skill_catalog
        self.events = event_bus or EventBus()
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # Session and run lifecycle ---------------------------------------

    def create_session(self, title: str = "新对话") -> AgentSession:
        skills: list[SkillIndexEntry] = []
        if self._skill_catalog is not None:
            for metadata in self._skill_catalog.discover().values():
                if metadata.disable_model_invocation:
                    continue
                version = str(metadata.path.stat().st_mtime_ns)
                skills.append(
                    SkillIndexEntry(
                        skill_id=metadata.name,
                        name=metadata.name,
                        description=metadata.description,
                        version=version,
                    )
                )
        prefix, prefix_hash, index_hash = self._definition.freeze_prefix(skills)
        return self.store.create_session(
            AgentSession(
                title=title,
                agent_id=self._definition.agent_id,
                agent_definition_version=self._definition.version,
                prefix_text=prefix,
                prefix_hash=prefix_hash,
                capability_index_hash=index_hash,
                model_profile_id=self._model_profile.profile_id,
            )
        )

    async def create_run(
        self,
        session_id: str,
        message: str,
        *,
        source: str = "chat",
        requested_skills: list[str] | None = None,
        artifact_ids: list[str] | None = None,
        principal_id: str = "local-user",
        max_steps: int = 24,
        max_seconds: int = 600,
    ) -> AgentRun:
        self.store.get_session(session_id)
        requested_skills = requested_skills or []
        if requested_skills:
            if self._skill_catalog is None:
                raise ValueError("skill catalog is unavailable")
            discovered = self._skill_catalog.discover()
            missing = [name for name in requested_skills if name not in discovered]
            if missing:
                raise ValueError(f"unknown requested skill: {missing[0]}")
        classifier = IntentClassifier(self._capabilities, skills=self._skill_metadata)
        intent = classifier.build(
            IntentRequest(
                message=message,
                source=source,
                principal_id=principal_id,
                requested_skills=requested_skills,
                max_steps=max_steps,
                max_seconds=max_seconds,
            )
        )
        status = (
            RunStatus.RUNNING_STRUCTURED
            if intent.path is RunPath.STRUCTURED
            else RunStatus.RUNNING_FAST
        )
        run = AgentRun(
            session_id=session_id,
            objective=message,
            path=intent.path,
            status=status,
            principal_id=principal_id,
            requested_skills=requested_skills,
            input_artifact_ids=artifact_ids or [],
            max_steps=max_steps,
            max_seconds=max_seconds,
        )
        initial = [
            self._event(
                run,
                AgentEventType.USER_MESSAGE,
                {
                    "content": message,
                    "source": source,
                    "skill_ids": requested_skills,
                    "artifact_ids": artifact_ids or [],
                },
            ),
            self._event(
                run,
                AgentEventType.RUN_CREATED,
                {"objective": message, "path": run.path.value, "status": run.status.value},
            ),
            self._event(
                run,
                AgentEventType.RUN_STATUS_CHANGED,
                {"from": "created", "to": status.value, "reason": "intent_selected"},
            ),
        ]
        run, saved = self.store.create_run_with_events(run, initial)
        self.events.publish(saved)

        if run.path is RunPath.STRUCTURED:
            plan, tasks = self._plan_manager.create_default(run)
            run = run.model_copy(update={"current_plan_id": plan.plan_id})
            run, saved = self.store.save_run_with_events(
                run,
                [
                    self._event(
                        run,
                        AgentEventType.PLAN_CREATED,
                        {
                            "plan_id": plan.plan_id,
                            "goal": plan.goal,
                            "tasks": [task.model_dump(mode="json") for task in tasks],
                        },
                    )
                ],
                expected_revision=run.revision,
            )
            self.events.publish(saved)
        for skill_id in requested_skills:
            run, skill_event, _ = self._activate_skill(run, skill_id, arguments="")
            run, saved = self.store.save_run_with_events(
                run, [skill_event], expected_revision=run.revision
            )
            self.events.publish(saved)
        return run

    async def execute(self, run_id: str) -> AgentRun:
        async with self._locks[run_id]:
            run = self.store.get_run(run_id)
            if run.status not in {RunStatus.RUNNING_FAST, RunStatus.RUNNING_STRUCTURED}:
                return run
            return await self._loop(run)

    async def _loop(self, run: AgentRun) -> AgentRun:
        started = monotonic()
        while run.status in {RunStatus.RUNNING_FAST, RunStatus.RUNNING_STRUCTURED}:
            if monotonic() - started >= run.max_seconds:
                return self._fail(run, "time_exhausted")
            exhausted = run.consumed_steps >= run.max_steps
            try:
                capabilities = [] if exhausted else self._available(run)
            except ValueError as error:
                return self._fail(run, str(error))
            session = self.store.get_session(run.session_id)
            try:
                working = self._working_content(run)
            except ValueError as error:
                return self._fail(run, str(error))
            if exhausted:
                working.append(
                    {
                        "role": "system",
                        "content": (
                            "The capability budget is exhausted. Give a final answer from verified "
                            "results and state what remains incomplete. Do not request another tool."
                        ),
                    }
                )
            context = self._context_builder.build(
                session,
                run,
                capabilities,
                self._model_profile,
                working_content=working,
            )
            context, run = await self._compact_if_needed(context, run, capabilities, working)
            if context.over_hard_limit:
                return self._fail(run, "context_hard_limit_exceeded")
            self.store.save_context_manifest(context.manifest)
            context_event = self.store.append_event(
                self._event(
                    run,
                    AgentEventType.CONTEXT_BUILT,
                    {
                        "turn_id": context.manifest.turn_id,
                        "checkpoint_id": context.manifest.checkpoint_id,
                        "token_breakdown": context.manifest.token_breakdown,
                        "estimated_prompt_tokens": context.projected_tokens,
                        "context_hash": context.manifest.context_hash,
                        "tool_versions": context.manifest.tool_versions,
                    },
                )
            )
            self.events.publish([context_event])
            bundle = ContextBundle(
                system_context=context.system_context,
                messages=context.messages,
                budget=BudgetReport(
                    limit=ContextPolicy.for_model(self._model_profile).hard_limit,
                    system_tokens=context.manifest.token_breakdown.get("prefix_tokens", 0),
                    messages_tokens=sum(
                        value
                        for key, value in context.manifest.token_breakdown.items()
                        if key not in {"prefix_tokens", "tool_schema_tokens"}
                    ),
                    tools_tokens=context.manifest.token_breakdown.get("tool_schema_tokens", 0),
                ),
            )
            action = await self._model.next_turn(bundle, capabilities, context.messages)
            if action.usage:
                self.store.update_context_usage(
                    context.manifest.turn_id,
                    {
                        str(key): int(value)
                        for key, value in action.usage.items()
                        if isinstance(value, int) and not isinstance(value, bool)
                    },
                )
            turn_event = self.store.append_event(
                self._event(
                    run,
                    AgentEventType.MODEL_TURN,
                    {
                        "kind": action.kind,
                        "turn_id": context.manifest.turn_id,
                        "usage": action.usage or {},
                    },
                )
            )
            self.events.publish([turn_event])
            if action.kind == "error":
                return self._fail(run, action.reason)
            if action.kind == "final":
                return self._complete(run, action.text)
            if exhausted:
                return self._fail(run, "capability_budget_exhausted")
            assert action.call is not None
            run = await self._handle_call(run, action)
        return run

    # Calls -------------------------------------------------------------

    async def _handle_call(self, run: AgentRun, action: ModelAction) -> AgentRun:
        assert action.call is not None
        control = action.call.arguments.pop("_maestro_context", None)
        arguments = dict(action.call.arguments)
        call = CapabilityCall(name=action.call.name, arguments=arguments)
        normalized = json.dumps(
            {"name": call.name, "arguments": call.arguments},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        prior = self.store.list_events(run.session_id, run_id=run.run_id, limit=10_000)
        repeats = sum(
            event.event_type is AgentEventType.TOOL_CALL
            and event.payload.get("normalized_call") == normalized
            for event in prior
        )
        if repeats >= 2:
            return self._fail(run, "cycle_detected")
        call_id = action.tool_call_id or f"call_{uuid4().hex}"
        evidence_ids = []
        if isinstance(control, dict) and isinstance(control.get("evidence_ids"), list):
            evidence_ids = [str(item) for item in control["evidence_ids"]]
        call_event = self._event(
            run,
            AgentEventType.TOOL_CALL,
            {
                "call_id": call_id,
                "tool_id": call.name,
                "arguments": arguments,
                "normalized_call": normalized,
            },
            references={"evidence_ids": evidence_ids},
        )
        run = run.model_copy(update={"consumed_steps": run.consumed_steps + 1})
        run, saved = self.store.save_run_with_events(
            run, [call_event], expected_revision=run.revision
        )
        self.events.publish(saved)

        try:
            spec = self._resolver.snapshot().require(call.name)
        except KeyError:
            return self._recoverable_failure(run, call, call_id, "unknown_capability")
        if not _arguments_match_schema(call.arguments, spec.input_schema):
            return self._recoverable_failure(run, call, call_id, "schema_input")

        if call.name == "tool_search":
            return self._tool_search(run, call, call_id)
        if call.name == "load_skill":
            return self._load_skill(run, call, call_id)
        if call.name == "get_current_plan":
            content: object = None
            if run.current_plan_id:
                plan, tasks = self.store.get_plan(run.current_plan_id)
                content = {
                    "plan": plan.model_dump(mode="json"),
                    "tasks": [task.model_dump(mode="json") for task in tasks],
                }
            return self._record_result(run, call, call_id, CapabilityResult(status="succeeded", content=content))
        if call.name == "get_result_detail":
            return self._get_result_detail(run, call, call_id)

        if call.name not in CORE_CAPABILITIES and call.name not in run.active_tool_versions:
            return self._recoverable_failure(
                run, call, call_id, "capability_not_activated; use tool_search first"
            )
        if run.active_tool_versions.get(call.name) not in {None, spec.version}:
            return self._fail(run, f"capability_version_unavailable:{call.name}")

        allowed = _skill_allowed_tools(run)
        decision = self._policy_gate.evaluate(
            call,
            spec,
            PolicyContext(
                principal_id=run.principal_id,
                skill_allowed_tools=allowed,
            ),
        )
        if decision.effect in {
            PolicyEffect.REQUIRE_CONFIRMATION,
            PolicyEffect.REQUIRE_RECONFIRMATION,
        }:
            if run.path is RunPath.FAST:
                run = self._upgrade(run, "side_effect_requires_controlled_execution")
            return await self._request_approval(run, call, call_id, spec, decision)
        if decision.effect is not PolicyEffect.ALLOW:
            return self._fail(run, decision.reason)
        if spec.executor is None:
            return self._recoverable_failure(run, call, call_id, "missing_executor")
        result = await self._execute(spec, call, None, principal_id=run.principal_id)
        return self._record_result(run, call, call_id, result, spec=spec)

    def _tool_search(self, run: AgentRun, call: CapabilityCall, call_id: str) -> AgentRun:
        query = str(call.arguments.get("query") or "").strip()
        if not query:
            return self._recoverable_failure(run, call, call_id, "query is required")
        namespace = call.arguments.get("namespace")
        search = self._resolver.search(
            query,
            namespace=str(namespace) if isinstance(namespace, str) and namespace else None,
            allowed=_skill_allowed_tools(run),
            top_k=int(call.arguments.get("top_k") or 5),
        )
        versions = dict(run.active_tool_versions)
        for candidate in search.candidates:
            versions[str(candidate["tool_id"])] = str(candidate["version"])
        run = run.model_copy(update={"active_tool_versions": versions})
        search_event = self._event(
            run,
            AgentEventType.TOOL_SEARCH,
            {
                "query": query,
                "namespace": search.namespace,
                "candidates": search.candidates,
            },
            references={"call_id": call_id},
        )
        result_event, _ = self._result_event(
            run,
            call,
            call_id,
            CapabilityResult(status="succeeded", content={"candidates": search.candidates}),
        )
        run, saved = self.store.save_run_with_events(
            run, [search_event, result_event], expected_revision=run.revision
        )
        self.events.publish(saved)
        return run

    def _get_result_detail(
        self, run: AgentRun, call: CapabilityCall, call_id: str
    ) -> AgentRun:
        requested_id = str(call.arguments.get("result_id") or "").strip()
        requested_id = requested_id.removeprefix("tool-result://")
        if not requested_id:
            return self._recoverable_failure(
                run, call, call_id, "result_id is required"
            )
        try:
            source = self.store.get_tool_result(
                requested_id, session_id=run.session_id
            )
            # Older Runtime versions persisted each dereference as another tool
            # result. Resolve those wrappers back to the original source so an
            # existing result_ref cannot keep nesting forever.
            seen = {requested_id}
            while source.get("tool_id") == "get_result_detail":
                wrapped = source.get("raw_payload")
                source_id = wrapped.get("result_id") if isinstance(wrapped, dict) else None
                if not isinstance(source_id, str) or source_id in seen:
                    break
                seen.add(source_id)
                source = self.store.get_tool_result(
                    source_id, session_id=run.session_id
                )
        except FileNotFoundError:
            return self._recoverable_failure(
                run, call, call_id, "result_not_found"
            )

        offset = int(call.arguments.get("offset") or 0)
        max_chars = int(call.arguments.get("max_chars") or 2000)
        max_chars = max(256, min(max_chars, 2500))
        encoded = json.dumps(
            source.get("raw_payload"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if offset < 0 or offset > len(encoded):
            return self._recoverable_failure(
                run, call, call_id, "result_offset_out_of_range"
            )
        end = min(len(encoded), offset + max_chars)
        source_id = str(source["result_id"])
        digest = {
            "source_result_id": source_id,
            "tool_id": source["tool_id"],
            "tool_version": source["tool_version"],
            "source_status": source["status"],
            "content_json_chunk": encoded[offset:end],
            "offset": offset,
            "next_offset": end if end < len(encoded) else None,
            "total_chars": len(encoded),
            "truncated": end < len(encoded),
            "external_ref": source.get("external_ref"),
        }
        event = self.store.append_event(
            self._event(
                run,
                AgentEventType.TOOL_RESULT,
                {
                    "tool_id": call.name,
                    "status": "succeeded",
                    "digest": digest,
                    "result_ref": f"tool-result://{source_id}",
                    "error": None,
                },
                references={"call_id": call_id},
            )
        )
        self.events.publish([event])
        return run

    def _load_skill(self, run: AgentRun, call: CapabilityCall, call_id: str) -> AgentRun:
        name = str(call.arguments.get("skill_id") or "")
        if not name:
            return self._recoverable_failure(run, call, call_id, "skill_unavailable")
        try:
            run, skill_event, result_content = self._activate_skill(
                run, name, arguments=str(call.arguments.get("arguments") or "")
            )
        except (KeyError, OSError, UnicodeError, ValueError):
            return self._recoverable_failure(run, call, call_id, "skill_unavailable")
        skill_event = skill_event.model_copy(update={"references": {"call_id": call_id}})
        result_event, _ = self._result_event(
            run,
            call,
            call_id,
            CapabilityResult(status="succeeded", content=result_content),
        )
        run, saved = self.store.save_run_with_events(
            run, [skill_event, result_event], expected_revision=run.revision
        )
        self.events.publish(saved)
        return run

    def _activate_skill(
        self, run: AgentRun, name: str, *, arguments: str
    ) -> tuple[AgentRun, AgentEvent, dict[str, object]]:
        if self._skill_catalog is None:
            raise ValueError("skill catalog is unavailable")
        metadata = self._skill_catalog.metadata(name)
        if metadata is None:
            self._skill_catalog.discover()
            metadata = self._skill_catalog.metadata(name)
        if metadata is None:
            raise KeyError(name)
        body = self._skill_catalog.load_body(name)
        version = str(metadata.path.stat().st_mtime_ns)
        self.store.sync_skill_definition(
            skill_id=name,
            version=version,
            name=metadata.name,
            description=metadata.description,
            body=body,
            metadata={
                "skill_dir": str(metadata.path.parent),
                "allowed_tools": list(metadata.allowed_tools),
                "mode": metadata.context,
            },
        )
        state = dict(run.working_state)
        skill_arguments = dict(state.get("skill_arguments", {}))
        skill_arguments[name] = arguments
        state["skill_arguments"] = skill_arguments
        current_allowed_raw = state.get("skill_allowed_tools")
        loaded_allowed = set(metadata.allowed_tools)
        if isinstance(current_allowed_raw, list):
            current_allowed = {str(item) for item in current_allowed_raw}
            if loaded_allowed:
                state["skill_allowed_tools"] = sorted(current_allowed & loaded_allowed)
        elif loaded_allowed:
            state["skill_allowed_tools"] = sorted(loaded_allowed)
        run = run.model_copy(
            update={
                "active_skill_versions": {**run.active_skill_versions, name: version},
                "working_state": state,
            }
        )
        event = self._event(
            run,
            AgentEventType.SKILL_ACTIVATED,
            {"skill_id": name, "version": version, "phase": "active"},
        )
        return run, event, {"skill_id": name, "version": version}

    async def _execute(
        self,
        spec: CapabilitySpec,
        call: CapabilityCall,
        idempotency_key: str | None,
        *,
        principal_id: str,
    ) -> CapabilityResult:
        try:
            if spec.executor is None:
                return CapabilityResult(status="failed", error_message="missing_executor")
            execution_call = call.model_copy(update={"principal_id": principal_id})
            return await spec.executor(execution_call, idempotency_key)
        except UnknownWriteOutcome:
            return CapabilityResult(status="unknown")
        except Exception as error:  # execution errors are data for the next model turn
            return CapabilityResult(
                status="failed",
                error_kind=RuntimeErrorKind.UNKNOWN_OR_BUG,
                error_message=f"capability_exception:{type(error).__name__}",
            )

    def _record_result(
        self,
        run: AgentRun,
        call: CapabilityCall,
        call_id: str,
        result: CapabilityResult,
        *,
        spec: CapabilitySpec | None = None,
    ) -> AgentRun:
        event, evidence = self._result_event(run, call, call_id, result, spec=spec)
        saved_events = [self.store.append_event(event)]
        if evidence:
            recall_event = self.store.append_event(
                self._event(
                    run,
                    AgentEventType.EVIDENCE_RECALLED,
                    {
                        "tool_id": call.name,
                        "items": [item.model_dump(mode="json") for item in evidence],
                    },
                    references={"call_id": call_id, "tool_result_event_id": event.event_id},
                )
            )
            saved_events.append(recall_event)
            for item in evidence:
                self.store.save_evidence(
                    item.model_copy(update={"recall_event_id": recall_event.event_id})
                )
        self.events.publish(saved_events)
        if result.status == "unknown":
            return self._set_status(run, RunStatus.RECONCILING, "unknown_write_outcome")
        return run

    def _result_event(
        self,
        run: AgentRun,
        call: CapabilityCall,
        call_id: str,
        result: CapabilityResult,
        *,
        spec: CapabilitySpec | None = None,
    ) -> tuple[AgentEvent, list[EvidenceRecord]]:
        content = result.content
        digest = _digest(content)
        result_id = self.store.put_tool_result(
            session_id=run.session_id,
            run_id=run.run_id,
            tool_id=call.name,
            tool_version=spec.version if spec else "2.0.0",
            status=result.status,
            digest=digest,
            raw_payload=content,
            external_ref=result.artifact_ref,
        )
        evidence: list[EvidenceRecord] = []
        for item in result.evidence:
            evidence.append(
                EvidenceRecord(
                    session_id=run.session_id,
                    run_id=run.run_id,
                    source_type=item.source_type,
                    source_ref=item.source_ref,
                    content_digest=item.content_digest,
                    validity=item.validity,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                )
            )
        if evidence:
            digest = {"items": [item.model_dump(mode="json") for item in evidence]}
        return (
            self._event(
                run,
                AgentEventType.TOOL_RESULT,
                {
                    "tool_id": call.name,
                    "status": result.status,
                    "digest": digest,
                    "result_ref": f"tool-result://{result_id}",
                    "error": result.error_message,
                },
                references={"call_id": call_id},
            ),
            evidence,
        )

    # Approval and governed writes ------------------------------------

    async def _request_approval(
        self,
        run: AgentRun,
        call: CapabilityCall,
        call_id: str,
        spec: CapabilitySpec,
        decision: Any,
    ) -> AgentRun:
        token = await spec.revalidator(call) if spec.revalidator else None
        allowed = _skill_allowed_tools(run)
        arguments_text = json.dumps(
            call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        schema_text = json.dumps(
            spec.input_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        approval = ApprovalState(
            run_id=run.run_id,
            session_id=run.session_id,
            tool_id=spec.name,
            tool_version=spec.version,
            schema_hash=hashlib.sha256(schema_text.encode()).hexdigest(),
            arguments=call.arguments,
            arguments_hash=hashlib.sha256(arguments_text.encode()).hexdigest(),
            idempotency_key=hashlib.sha256(
                f"{run.session_id}:{run.run_id}:{spec.name}:{arguments_text}".encode()
            ).hexdigest(),
            impact_summary=f"write via {spec.name}",
            policy_reason=decision.reason,
            external_state_token=token,
            run_revision=run.revision + 1,
            skill_allowed_tools=(
                sorted(allowed) if allowed is not None else None
            ),
            confirmations_required=(
                2 if decision.effect is PolicyEffect.REQUIRE_RECONFIRMATION else 1
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self.store.save_approval(approval)
        working_state = {**run.working_state, "pending_call_id": call_id}
        run = run.model_copy(
            update={
                "pending_approval_id": approval.approval_id,
                "working_state": working_state,
            }
        )
        run = self._set_status(
            run,
            RunStatus.WAITING_APPROVAL,
            "approval_required",
            extra_events=[
                self._event(
                    run,
                    AgentEventType.APPROVAL_REQUESTED,
                    approval.model_dump(mode="json"),
                )
            ],
        )
        return run

    async def resolve_approval(
        self,
        run_id: str,
        approval_id: str,
        *,
        approved: bool,
        principal_id: str,
        expected_revision: int,
    ) -> AgentRun:
        async with self._locks[run_id]:
            run = self.store.get_run(run_id)
            if (
                run.status is not RunStatus.WAITING_APPROVAL
                or run.revision != expected_revision
                or run.pending_approval_id != approval_id
            ):
                raise ValueError("stale approval revision")
            approval = self.store.get_approval(approval_id)
            if approval.status != "pending" or approval.expires_at <= datetime.now(UTC):
                raise ValueError("approval is stale or expired")
            if not approved:
                self.store.update_approval(
                    approval.model_copy(update={"status": "rejected"}), "pending"
                )
                return self._fail(
                    run,
                    "approval_rejected",
                    extra_events=[
                        self._event(
                            run,
                            AgentEventType.APPROVAL_RESOLVED,
                            {"approval_id": approval_id, "approved": False},
                        )
                    ],
                )
            try:
                spec = self._resolver.snapshot().require(approval.tool_id)
            except KeyError as error:
                raise ValueError("capability version unavailable") from error
            if spec.version != approval.tool_version:
                raise ValueError("capability version unavailable")
            call = CapabilityCall(name=approval.tool_id, arguments=approval.arguments)
            decision = self._policy_gate.evaluate(
                call,
                spec,
                PolicyContext(
                    principal_id=principal_id,
                    skill_allowed_tools=(
                        set(approval.skill_allowed_tools)
                        if approval.skill_allowed_tools is not None
                        else None
                    ),
                ),
            )
            if decision.effect is PolicyEffect.DENY:
                return self._fail(run, decision.reason)
            token = await spec.revalidator(call) if spec.revalidator else None
            if token != approval.external_state_token:
                raise ValueError("external state changed")
            confirmations = [*approval.confirmations, principal_id]
            if len(confirmations) < approval.confirmations_required:
                self.store.update_approval(
                    approval.model_copy(
                        update={"status": "approved", "confirmations": confirmations}
                    ),
                    "pending",
                )
                replacement = approval.model_copy(
                    update={
                        "approval_id": str(uuid4()),
                        "status": "pending",
                        "confirmations": confirmations,
                        "run_revision": run.revision + 1,
                        "external_state_token": token,
                        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
                    }
                )
                self.store.save_approval(replacement)
                run = run.model_copy(update={"pending_approval_id": replacement.approval_id})
                run, saved = self.store.save_run_with_events(
                    run,
                    [
                        self._event(
                            run,
                            AgentEventType.APPROVAL_RESOLVED,
                            {"approval_id": approval_id, "approved": True, "final": False},
                        ),
                        self._event(
                            run,
                            AgentEventType.APPROVAL_REQUESTED,
                            replacement.model_dump(mode="json"),
                        ),
                    ],
                    expected_revision=run.revision,
                )
                self.events.publish(saved)
                return run
            self.store.update_approval(
                approval.model_copy(
                    update={"status": "approved", "confirmations": confirmations}
                ),
                "pending",
            )
            call_id = str(run.working_state.get("pending_call_id") or f"approved_{approval_id}")
            working_state = dict(run.working_state)
            working_state.pop("pending_call_id", None)
            run = run.model_copy(
                update={"pending_approval_id": None, "working_state": working_state}
            )
            run = self._set_status(
                run,
                RunStatus.RUNNING_STRUCTURED,
                "approval_granted",
                extra_events=[
                    self._event(
                        run,
                        AgentEventType.APPROVAL_RESOLVED,
                        {"approval_id": approval_id, "approved": True, "final": True},
                    )
                ],
            )
            result = await self._execute(
                spec,
                call,
                approval.idempotency_key,
                principal_id=run.principal_id,
            )
            run = self._record_result(
                run,
                call,
                call_id,
                result,
                spec=spec,
            )
            if run.status is RunStatus.RUNNING_STRUCTURED:
                return await self._loop(run)
            return run

    async def cancel(self, run_id: str) -> AgentRun:
        async with self._locks[run_id]:
            run = self.store.get_run(run_id)
            if run.status in TERMINAL_STATUSES:
                return run
            if run.status is RunStatus.RECONCILING:
                return run
            run = self._set_status(run, RunStatus.CANCELLING, "cancel_requested")
            return self._set_status(run, RunStatus.CANCELLED, "cancelled")

    # State helpers -----------------------------------------------------

    async def _compact_if_needed(
        self,
        context: SessionContext,
        run: AgentRun,
        capabilities: list[CapabilitySpec],
        working: list[dict],
    ) -> tuple[SessionContext, AgentRun]:
        policy = ContextPolicy.for_model(self._model_profile)
        if context.projected_tokens < policy.compact_trigger:
            return context, run
        events = self.store.list_events(run.session_id, limit=10_000)
        if len(events) <= 6:
            return context, run
        force = context.projected_tokens >= policy.force_compact_trigger
        checkpoint = await self._checkpoint_manager.compact(
            run.session_id,
            covered_until_sequence=events[-7].sequence,
            build_type="force" if force else "incremental",
        )
        if checkpoint is not None:
            event = self.store.append_event(
                self._event(
                    run,
                    AgentEventType.CHECKPOINT_CREATED,
                    {
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "generation": checkpoint.generation,
                        "covered_until_sequence": checkpoint.covered_until_sequence,
                        "build_type": checkpoint.build_type,
                    },
                )
            )
            self.events.publish([event])
        session = self.store.get_session(run.session_id)
        return (
            self._context_builder.build(
                session,
                run,
                capabilities,
                self._model_profile,
                working_content=working,
            ),
            run,
        )

    def _available(self, run: AgentRun) -> list[CapabilitySpec]:
        allowed = _skill_allowed_tools(run)
        return self._resolver.resolve(
            run.active_tool_versions,
            include_core=True,
            allowed=allowed,
        )

    def _working_content(self, run: AgentRun) -> list[dict]:
        arguments = run.working_state.get("skill_arguments", {})
        arguments = arguments if isinstance(arguments, dict) else {}
        content: list[dict] = []
        for name, version in run.active_skill_versions.items():
            try:
                definition = self.store.get_skill_definition(name, version)
            except FileNotFoundError as error:
                raise ValueError(f"skill_version_unavailable:{name}@{version}") from error
            metadata = definition.get("metadata")
            skill_dir = metadata.get("skill_dir", "") if isinstance(metadata, dict) else ""
            prompt = str(definition["body"])
            prompt = prompt.replace("$ARGUMENTS", str(arguments.get(name, "")))
            prompt = prompt.replace("${CLAUDE_SKILL_DIR}", str(skill_dir))
            prompt = prompt.replace("${CLAUDE_SESSION_ID}", run.session_id)
            content.append(
                {
                    "role": "system",
                    "content": (
                        f'<skill-guidance id="{name}" version="{version}">\n'
                        "This guidance is lower priority than the system and policy rules.\n"
                        f"{prompt}\n</skill-guidance>"
                    ),
                }
            )
        return content

    def _complete(self, run: AgentRun, text: str) -> AgentRun:
        envelope = _parse_envelope(text)
        extra: list[AgentEvent] = []
        evidence_records: dict[str, EvidenceRecord] = {}
        for usage in envelope.evidence_usage:
            try:
                evidence_records[usage.evidence_id] = self.store.get_evidence(
                    usage.evidence_id, session_id=run.session_id
                )
            except FileNotFoundError:
                return self._fail(run, f"unknown_evidence:{usage.evidence_id}")
        for usage in envelope.evidence_usage:
            saved = self.store.save_evidence_usage(
                EvidenceUsage(
                    session_id=run.session_id,
                    run_id=run.run_id,
                    evidence_id=usage.evidence_id,
                    derived_fact=usage.derived_fact,
                    usage_type=usage.usage_type,
                    future_relevant=usage.future_relevant,
                )
            )
            extra.append(
                self._event(
                    run,
                    AgentEventType.EVIDENCE_USED,
                    {
                        **saved.model_dump(mode="json"),
                        "source_type": evidence_records[usage.evidence_id].source_type,
                        "source_ref": evidence_records[usage.evidence_id].source_ref,
                        "validity": evidence_records[usage.evidence_id].validity,
                        "observed_at": evidence_records[usage.evidence_id].observed_at,
                    },
                )
            )
        if run.current_plan_id:
            for task in self._plan_manager.complete_all(run.current_plan_id):
                extra.append(
                    self._event(
                        run,
                        AgentEventType.PLAN_STEP_UPDATED,
                        {
                            "plan_id": run.current_plan_id,
                            "task_id": task.task_id,
                            "status": task.status.value,
                        },
                    )
                )
        extra.extend(_delta_events(run, envelope.state_delta))
        extra.append(
            self._event(
                run,
                AgentEventType.ASSISTANT_MESSAGE,
                {"content": envelope.answer},
            )
        )
        run = run.model_copy(update={"final_text": envelope.answer})
        return self._set_status(
            run,
            RunStatus.COMPLETED,
            "model_final",
            extra_events=extra,
        )

    def _fail(
        self, run: AgentRun, reason: str, *, extra_events: list[AgentEvent] | None = None
    ) -> AgentRun:
        run = run.model_copy(update={"error_code": reason})
        return self._set_status(
            run,
            RunStatus.FAILED,
            reason,
            extra_events=[
                *(extra_events or []),
                self._event(run, AgentEventType.ERROR, {"code": reason}),
            ],
        )

    def _recoverable_failure(
        self, run: AgentRun, call: CapabilityCall, call_id: str, message: str
    ) -> AgentRun:
        return self._record_result(
            run,
            call,
            call_id,
            CapabilityResult(status="failed", error_message=message),
        )

    def _upgrade(self, run: AgentRun, reason: str) -> AgentRun:
        if run.path is RunPath.STRUCTURED:
            return run
        run = self._set_status(run, RunStatus.STRUCTURING, reason)
        run = run.model_copy(update={"path": RunPath.STRUCTURED})
        if run.current_plan_id is None:
            plan, tasks = self._plan_manager.create_default(run)
            run = run.model_copy(update={"current_plan_id": plan.plan_id})
            events = [
                self._event(
                    run,
                    AgentEventType.PLAN_CREATED,
                    {
                        "plan_id": plan.plan_id,
                        "goal": plan.goal,
                        "tasks": [task.model_dump(mode="json") for task in tasks],
                    },
                )
            ]
        else:
            events = []
        return self._set_status(run, RunStatus.RUNNING_STRUCTURED, reason, extra_events=events)

    def _set_status(
        self,
        run: AgentRun,
        target: RunStatus,
        reason: str,
        *,
        extra_events: list[AgentEvent] | None = None,
    ) -> AgentRun:
        previous = run.status
        if target not in RUN_TRANSITIONS[previous]:
            raise ValueError(
                f"invalid run transition {previous.value} -> {target.value}: {reason}"
            )
        run = run.model_copy(update={"status": target})
        status_event = self._event(
            run,
            AgentEventType.RUN_STATUS_CHANGED,
            {"from": previous.value, "to": target.value, "reason": reason},
        )
        run, saved = self.store.save_run_with_events(
            run,
            [*(extra_events or []), status_event],
            expected_revision=run.revision,
        )
        self.events.publish(saved)
        return run

    def _event(
        self,
        run: AgentRun,
        event_type: AgentEventType,
        payload: dict[str, object],
        *,
        metadata: dict[str, object] | None = None,
        references: dict[str, object] | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            session_id=run.session_id,
            run_id=run.run_id,
            event_type=event_type,
            payload=payload,
            metadata=metadata or {},
            references=references or {},
        )

    def _skill_metadata(self) -> dict:
        return self._skill_catalog.discover() if self._skill_catalog is not None else {}


def _parse_envelope(text: str) -> TurnEnvelope:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            return TurnEnvelope.model_validate_json(stripped)
        except ValueError:
            pass
    return TurnEnvelope(answer=text)


def _delta_events(run: AgentRun, delta: StateDelta) -> list[AgentEvent]:
    events: list[AgentEvent] = []

    def event(kind: AgentEventType, payload: dict[str, object]) -> AgentEvent:
        return AgentEvent(
            session_id=run.session_id,
            run_id=run.run_id,
            event_type=kind,
            payload=payload,
        )

    events.extend(
        event(
            AgentEventType.CONSTRAINT_ADDED,
            {
                "constraint_id": item.constraint_id,
                "content": item.value,
                "source_ref": item.source_ref,
                "scope": item.scope,
            },
        )
        for item in delta.constraints_added
    )
    events.extend(
        event(AgentEventType.CONSTRAINT_REMOVED, {"constraint_id": identifier})
        for identifier in delta.constraint_ids_removed
    )
    events.extend(
        event(
            AgentEventType.DECISION_UPDATED,
            {
                "decision_id": item.decision_id,
                "content": item.value,
                "source_ref": item.source_ref,
                "supersedes": item.supersedes,
            },
        )
        for item in delta.decisions_added
    )
    return events


def _digest(content: object) -> object:
    if isinstance(content, dict):
        summary = content.get("summary")
        if isinstance(summary, str):
            return {"summary": summary[:2000]}
        encoded = json.dumps(content, ensure_ascii=False, default=str)
        if len(encoded) <= 4000:
            return content
        return {"summary": encoded[:2000] + "…", "truncated": True}
    if isinstance(content, str):
        return content if len(content) <= 2000 else content[:2000] + "…"
    return content


def _skill_allowed_tools(run: AgentRun) -> set[str] | None:
    raw = run.working_state.get("skill_allowed_tools")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    return {str(item) for item in raw}


def _arguments_match_schema(arguments: dict[str, object], schema: dict[str, object]) -> bool:
    if not schema:
        return True
    required = schema.get("required", [])
    if not isinstance(required, list) or any(
        not isinstance(key, str) or key not in arguments for key in required
    ):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return True
    types = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in arguments.items():
        declared = properties.get(key)
        if not isinstance(declared, dict) or not isinstance(declared.get("type"), str):
            continue
        expected = types.get(declared["type"])
        if expected is not None and (
            not isinstance(value, expected)
            or declared["type"] in {"integer", "number"}
            and isinstance(value, bool)
        ):
            return False
    return True
