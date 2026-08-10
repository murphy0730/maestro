"""Deterministic checkpoint reduction and compaction boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.tokens import estimate_tokens
from maestro.runtime.trajectory import (
    ActiveSkillState,
    AgentEvent,
    AgentEventType,
    CheckpointRecord,
    CheckpointState,
    ConstraintState,
    DecisionState,
    EvidenceUsage,
    FactState,
    SourceRef,
    StateDelta,
)


class StateDeltaExtractor(Protocol):
    async def extract(
        self, previous: CheckpointState, events: Sequence[AgentEvent]
    ) -> StateDelta: ...


class DeterministicDeltaExtractor:
    """Extract state from explicit control events without guessing free-form text."""

    async def extract(
        self, previous: CheckpointState, events: Sequence[AgentEvent]
    ) -> StateDelta:
        delta = StateDelta()
        for event in events:
            payload = event.payload
            reference = f"event://{event.event_id}"
            if event.event_type is AgentEventType.RUN_CREATED and not previous.primary_goal:
                objective = payload.get("objective")
                if isinstance(objective, str):
                    delta.goal, delta.goal_source_ref = objective, reference
            elif event.event_type is AgentEventType.CONSTRAINT_ADDED:
                content = payload.get("content")
                identifier = payload.get("constraint_id")
                if isinstance(content, str) and isinstance(identifier, str):
                    delta.constraints_added.append(
                        ConstraintState(
                            constraint_id=identifier,
                            value=content,
                            source_ref=str(payload.get("source_ref") or reference),
                            scope=str(payload.get("scope") or "session"),
                        )
                    )
            elif event.event_type is AgentEventType.CONSTRAINT_REMOVED:
                identifier = payload.get("constraint_id")
                if isinstance(identifier, str):
                    delta.constraint_ids_removed.append(identifier)
            elif event.event_type is AgentEventType.DECISION_UPDATED:
                content = payload.get("content")
                identifier = payload.get("decision_id")
                if isinstance(content, str) and isinstance(identifier, str):
                    delta.decisions_added.append(
                        DecisionState(
                            decision_id=identifier,
                            value=content,
                            source_ref=str(payload.get("source_ref") or reference),
                            supersedes=payload.get("supersedes")
                            if isinstance(payload.get("supersedes"), str)
                            else None,
                        )
                    )
            elif event.event_type is AgentEventType.SKILL_ACTIVATED:
                skill_id, version = payload.get("skill_id"), payload.get("version")
                if isinstance(skill_id, str) and isinstance(version, str):
                    delta.active_skills.append(
                        ActiveSkillState(
                            skill_id=skill_id,
                            version=version,
                            phase=str(payload.get("phase") or "active"),
                        )
                    )
            elif event.event_type is AgentEventType.EVIDENCE_USED and bool(
                payload.get("future_relevant")
            ):
                evidence_id = payload.get("evidence_id")
                derived_fact = payload.get("derived_fact")
                source_ref = payload.get("source_ref")
                source_type = payload.get("source_type")
                if all(isinstance(item, str) for item in (evidence_id, derived_fact, source_ref, source_type)):
                    delta.facts_added.append(
                        FactState(
                            fact_id=f"fact:{evidence_id}",
                            value=derived_fact,
                            source=SourceRef(
                                source_type=source_type,
                                source_ref=source_ref,
                                evidence_id=evidence_id,
                            ),
                            validity=str(payload.get("validity") or "stable"),
                            observed_at=payload.get("observed_at"),
                            refresh_after=payload.get("refresh_after"),
                        )
                    )
        return delta


def reduce_checkpoint(previous: CheckpointState, delta: StateDelta) -> CheckpointState:
    constraints = {item.constraint_id: item for item in previous.constraints}
    for identifier in delta.constraint_ids_removed:
        constraints.pop(identifier, None)
    constraints.update({item.constraint_id: item for item in delta.constraints_added})

    superseded = set(delta.decision_ids_superseded)
    superseded.update(
        item.supersedes for item in delta.decisions_added if item.supersedes is not None
    )
    decisions = {
        item.decision_id: item
        for item in previous.decisions
        if item.decision_id not in superseded
    }
    decisions.update({item.decision_id: item for item in delta.decisions_added})

    invalid_facts = set(delta.fact_ids_invalidated)
    facts = {item.fact_id: item for item in previous.facts if item.fact_id not in invalid_facts}
    facts.update({item.fact_id: item for item in delta.facts_added})

    skills = {item.skill_id: item for item in previous.active_skills}
    skills.update({item.skill_id: item for item in delta.active_skills})

    completed = list(dict.fromkeys([*previous.completed_actions, *delta.actions_completed]))
    completed_set = set(completed)
    pending = [
        item
        for item in dict.fromkeys([*previous.pending_actions, *delta.actions_pending])
        if item not in completed_set
    ]
    return previous.model_copy(
        update={
            "primary_goal": delta.goal or previous.primary_goal,
            "goal_source_ref": delta.goal_source_ref or previous.goal_source_ref,
            "constraints": list(constraints.values()),
            "decisions": list(decisions.values()),
            "current_state": {**previous.current_state, **delta.state_changes},
            "facts": list(facts.values()),
            "completed_actions": completed,
            "pending_actions": pending,
            "active_skills": list(skills.values()),
            "confirmations": {**previous.confirmations, **delta.confirmations},
        }
    )


class CheckpointManager:
    def __init__(self, store: SQLiteStore, extractor: StateDeltaExtractor | None = None) -> None:
        self._store = store
        self._extractor = extractor or DeterministicDeltaExtractor()

    async def compact(
        self,
        session_id: str,
        *,
        covered_until_sequence: int,
        build_type: str = "incremental",
    ) -> CheckpointRecord | None:
        previous = self._store.latest_checkpoint(session_id)
        after = previous.covered_until_sequence if previous is not None else 0
        events = [
            event
            for event in self._store.list_events(session_id, after_sequence=after, limit=10_000)
            if event.sequence <= covered_until_sequence
        ]
        if not events:
            return previous
        baseline = previous.state if previous is not None else CheckpointState()
        delta = await self._extractor.extract(baseline, events)
        state = reduce_checkpoint(baseline, delta)
        checkpoint = CheckpointRecord(
            session_id=session_id,
            parent_checkpoint_id=previous.checkpoint_id if previous else None,
            generation=(previous.generation + 1) if previous else 1,
            covered_until_sequence=events[-1].sequence,
            state=state,
            token_count=estimate_tokens(state.model_dump_json()),
            build_type=build_type,
        )
        return self._store.save_checkpoint(checkpoint)

    async def full_rebase(self, session_id: str, *, chunk_size: int = 200) -> CheckpointRecord | None:
        events = self._store.list_events(session_id, limit=10_000)
        if not events:
            return None
        state = CheckpointState()
        for start in range(0, len(events), chunk_size):
            delta = await self._extractor.extract(state, events[start : start + chunk_size])
            state = reduce_checkpoint(state, delta)
        previous = self._store.latest_checkpoint(session_id)
        checkpoint = CheckpointRecord(
            session_id=session_id,
            parent_checkpoint_id=previous.checkpoint_id if previous else None,
            generation=(previous.generation + 1) if previous else 1,
            covered_until_sequence=events[-1].sequence,
            state=state,
            token_count=estimate_tokens(state.model_dump_json()),
            build_type="full_rebase",
        )
        return self._store.save_checkpoint(checkpoint)
