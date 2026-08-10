"""SQLite persistence for the v2 event-driven agent runtime."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from maestro.runtime.trajectory import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentSession,
    ApprovalState,
    CheckpointRecord,
    ContextManifest,
    EvidenceRecord,
    EvidenceUsage,
    PlanRecord,
    PlanStatus,
    PlanTaskRecord,
    utc_now,
)


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_id(value: str, label: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


class SessionBusy(RuntimeError):
    """A session already owns a non-terminal main Run."""


class SQLiteStore:
    """Small transactional store; events and their projections commit together."""

    SCHEMA_VERSION = 2

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(f"database schema {version} is newer than supported")
            if version == 0:
                connection.executescript(_SCHEMA_V1)
                connection.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
            elif version == 1:
                connection.execute(
                    "ALTER TABLE agent_run ADD COLUMN input_artifact_ids_json TEXT NOT NULL DEFAULT '[]'"
                )
                connection.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")

    # Sessions and Runs -------------------------------------------------

    def create_session(self, session: AgentSession) -> AgentSession:
        _validate_id(session.session_id, "session identifier")
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO agent_session(
                    session_id,title,agent_id,agent_definition_version,prefix_text,prefix_hash,
                    capability_index_hash,model_profile_id,status,active_run_id,next_event_sequence,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session.session_id,
                    session.title,
                    session.agent_id,
                    session.agent_definition_version,
                    session.prefix_text,
                    session.prefix_hash,
                    session.capability_index_hash,
                    session.model_profile_id,
                    session.status,
                    session.active_run_id,
                    session.next_event_sequence,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
        return session

    def get_session(self, session_id: str) -> AgentSession:
        _validate_id(session_id, "session identifier")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_session WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(session_id)
        return _session(row)

    def list_sessions(self) -> list[AgentSession]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_session ORDER BY updated_at DESC"
            ).fetchall()
        return [_session(row) for row in rows]

    def rename_session(self, session_id: str, title: str) -> AgentSession:
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                "UPDATE agent_session SET title=?,updated_at=? WHERE session_id=?",
                (title, _now(), session_id),
            ).rowcount
            if changed != 1:
                raise FileNotFoundError(session_id)
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self.transaction(write=True) as connection:
            return connection.execute(
                "DELETE FROM agent_session WHERE session_id=?", (session_id,)
            ).rowcount == 1

    def create_run_with_events(
        self, run: AgentRun, events: Sequence[AgentEvent]
    ) -> tuple[AgentRun, list[AgentEvent]]:
        _validate_id(run.session_id, "session identifier")
        with self.transaction(write=True) as connection:
            session = connection.execute(
                "SELECT active_run_id FROM agent_session WHERE session_id=?", (run.session_id,)
            ).fetchone()
            if session is None:
                raise FileNotFoundError(run.session_id)
            if session["active_run_id"] is not None and run.parent_run_id is None:
                raise SessionBusy(run.session_id)
            self._insert_run(connection, run)
            if run.parent_run_id is None:
                connection.execute(
                    "UPDATE agent_session SET active_run_id=?,updated_at=? WHERE session_id=?",
                    (run.run_id, _now(), run.session_id),
                )
            saved = [self._append_event(connection, event) for event in events]
        return run, saved

    @staticmethod
    def _insert_run(connection: sqlite3.Connection, run: AgentRun) -> None:
        connection.execute(
            """
            INSERT INTO agent_run(
                run_id,session_id,parent_run_id,objective,path,status,principal_id,
                requested_skills_json,input_artifact_ids_json,active_skill_versions_json,active_tool_versions_json,
                consumed_steps,max_steps,max_seconds,revision,current_plan_id,pending_approval_id,
                final_text,error_code,working_state_json,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run.run_id,
                run.session_id,
                run.parent_run_id,
                run.objective,
                run.path.value,
                run.status.value,
                run.principal_id,
                _json(run.requested_skills),
                _json(run.input_artifact_ids),
                _json(run.active_skill_versions),
                _json(run.active_tool_versions),
                run.consumed_steps,
                run.max_steps,
                run.max_seconds,
                run.revision,
                run.current_plan_id,
                run.pending_approval_id,
                run.final_text,
                run.error_code,
                _json(run.working_state),
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
            ),
        )

    def get_run(self, run_id: str) -> AgentRun:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_run WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(run_id)
        return _run(row)

    def list_runs(self, session_id: str | None = None) -> list[AgentRun]:
        with self.transaction() as connection:
            if session_id is None:
                rows = connection.execute(
                    "SELECT * FROM agent_run ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM agent_run WHERE session_id=? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
        return [_run(row) for row in rows]

    def save_run_with_events(
        self,
        run: AgentRun,
        events: Sequence[AgentEvent],
        *,
        expected_revision: int,
    ) -> tuple[AgentRun, list[AgentEvent]]:
        updated = utc_now()
        run = run.model_copy(update={"revision": expected_revision + 1, "updated_at": updated})
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                """
                UPDATE agent_run SET
                    path=?,status=?,requested_skills_json=?,active_skill_versions_json=?,
                    input_artifact_ids_json=?,active_tool_versions_json=?,consumed_steps=?,max_steps=?,max_seconds=?,revision=?,
                    current_plan_id=?,pending_approval_id=?,final_text=?,error_code=?,working_state_json=?,
                    updated_at=?
                WHERE run_id=? AND revision=?
                """,
                (
                    run.path.value,
                    run.status.value,
                    _json(run.requested_skills),
                    _json(run.active_skill_versions),
                    _json(run.input_artifact_ids),
                    _json(run.active_tool_versions),
                    run.consumed_steps,
                    run.max_steps,
                    run.max_seconds,
                    run.revision,
                    run.current_plan_id,
                    run.pending_approval_id,
                    run.final_text,
                    run.error_code,
                    _json(run.working_state),
                    updated.isoformat(),
                    run.run_id,
                    expected_revision,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("stale run revision")
            terminal = run.status.value in {"completed", "failed", "cancelled"}
            if terminal and run.parent_run_id is None:
                connection.execute(
                    """
                    UPDATE agent_session SET active_run_id=NULL,updated_at=?
                    WHERE session_id=? AND active_run_id=?
                    """,
                    (updated.isoformat(), run.session_id, run.run_id),
                )
            saved = [self._append_event(connection, event) for event in events]
        return run, saved

    # Events ------------------------------------------------------------

    def append_event(self, event: AgentEvent) -> AgentEvent:
        with self.transaction(write=True) as connection:
            return self._append_event(connection, event)

    @staticmethod
    def _append_event(connection: sqlite3.Connection, event: AgentEvent) -> AgentEvent:
        row = connection.execute(
            "SELECT next_event_sequence FROM agent_session WHERE session_id=?",
            (event.session_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(event.session_id)
        sequence = int(row["next_event_sequence"])
        saved = event.model_copy(update={"sequence": sequence})
        connection.execute(
            "UPDATE agent_session SET next_event_sequence=?,updated_at=? WHERE session_id=?",
            (sequence + 1, saved.created_at.isoformat(), event.session_id),
        )
        connection.execute(
            """
            INSERT INTO agent_event(
                event_id,session_id,run_id,sequence_no,event_type,payload_json,metadata_json,
                references_json,token_count,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                saved.event_id,
                saved.session_id,
                saved.run_id,
                saved.sequence,
                saved.event_type.value,
                _json(saved.payload),
                _json(saved.metadata),
                _json(saved.references),
                saved.token_count,
                saved.created_at.isoformat(),
            ),
        )
        return saved

    def get_event(self, event_id: str) -> AgentEvent:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_event WHERE event_id=?", (event_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(event_id)
        return _event(row)

    def list_events(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
        run_id: str | None = None,
        limit: int = 1000,
    ) -> list[AgentEvent]:
        clauses = ["session_id=?", "sequence_no>?"]
        values: list[object] = [session_id, after_sequence]
        if run_id is not None:
            clauses.append("run_id=?")
            values.append(run_id)
        values.append(max(1, min(limit, 10_000)))
        with self.transaction() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_event WHERE {' AND '.join(clauses)} "
                "ORDER BY sequence_no LIMIT ?",
                values,
            ).fetchall()
        return [_event(row) for row in rows]

    def redact_message(self, session_id: str, event_id: str, *, cascade: bool = False) -> list[str]:
        with self.transaction(write=True) as connection:
            target = connection.execute(
                "SELECT * FROM agent_event WHERE session_id=? AND event_id=?",
                (session_id, event_id),
            ).fetchone()
            if target is None or target["event_type"] not in {
                AgentEventType.USER_MESSAGE.value,
                AgentEventType.ASSISTANT_MESSAGE.value,
            }:
                raise FileNotFoundError(event_id)
            targets = [target["event_id"]]
            if cascade and target["event_type"] == AgentEventType.USER_MESSAGE.value:
                following = connection.execute(
                    """
                    SELECT event_id,event_type FROM agent_event
                    WHERE session_id=? AND sequence_no>? ORDER BY sequence_no
                    """,
                    (session_id, target["sequence_no"]),
                ).fetchall()
                for row in following:
                    if row["event_type"] == AgentEventType.USER_MESSAGE.value:
                        break
                    if row["event_type"] == AgentEventType.ASSISTANT_MESSAGE.value:
                        targets.append(row["event_id"])
            redaction = AgentEvent(
                session_id=session_id,
                run_id=target["run_id"],
                event_type=AgentEventType.MESSAGE_REDACTED,
                payload={"target_event_ids": targets},
                references={"source_event_id": event_id},
            )
            self._append_event(connection, redaction)
        return targets

    def message_events(self, session_id: str) -> list[AgentEvent]:
        events = self.list_events(session_id, limit=10_000)
        redacted = {
            str(target)
            for event in events
            if event.event_type is AgentEventType.MESSAGE_REDACTED
            for target in event.payload.get("target_event_ids", [])
        }
        return [
            event
            for event in events
            if event.event_type in {
                AgentEventType.USER_MESSAGE,
                AgentEventType.ASSISTANT_MESSAGE,
            }
            and event.event_id not in redacted
        ]

    # Checkpoints and plans --------------------------------------------

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        with self.transaction(write=True) as connection:
            latest = connection.execute(
                """
                SELECT generation,covered_until_sequence FROM session_checkpoint
                WHERE session_id=? ORDER BY generation DESC LIMIT 1
                """,
                (checkpoint.session_id,),
            ).fetchone()
            if latest is not None:
                if checkpoint.generation != int(latest["generation"]) + 1:
                    raise ValueError("checkpoint generation is not continuous")
                if checkpoint.covered_until_sequence <= int(latest["covered_until_sequence"]):
                    raise ValueError("checkpoint coverage must increase")
            elif checkpoint.generation != 1:
                raise ValueError("first checkpoint generation must be 1")
            connection.execute(
                """
                INSERT INTO session_checkpoint(
                    checkpoint_id,session_id,parent_checkpoint_id,generation,
                    covered_until_sequence,state_json,token_count,build_type,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.session_id,
                    checkpoint.parent_checkpoint_id,
                    checkpoint.generation,
                    checkpoint.covered_until_sequence,
                    checkpoint.state.model_dump_json(),
                    checkpoint.token_count,
                    checkpoint.build_type,
                    checkpoint.created_at.isoformat(),
                ),
            )
        return checkpoint

    def latest_checkpoint(self, session_id: str) -> CheckpointRecord | None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM session_checkpoint WHERE session_id=?
                ORDER BY generation DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return _checkpoint(row) if row is not None else None

    def list_checkpoints(self, session_id: str) -> list[CheckpointRecord]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM session_checkpoint WHERE session_id=? ORDER BY generation",
                (session_id,),
            ).fetchall()
        return [_checkpoint(row) for row in rows]

    def create_plan(self, plan: PlanRecord, tasks: Sequence[PlanTaskRecord]) -> PlanRecord:
        _validate_plan_tasks(tasks)
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO plan(plan_id,session_id,run_id,goal,status,version,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    plan.plan_id,
                    plan.session_id,
                    plan.run_id,
                    plan.goal,
                    plan.status.value,
                    plan.version,
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                ),
            )
            for task in tasks:
                connection.execute(
                    """
                    INSERT INTO plan_task(
                        task_id,plan_id,parent_task_id,title,description,status,priority,
                        sequence_no,depends_on_json,started_at,completed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        task.task_id,
                        task.plan_id,
                        task.parent_task_id,
                        task.title,
                        task.description,
                        task.status.value,
                        task.priority,
                        task.sequence,
                        _json(task.depends_on),
                        task.started_at.isoformat() if task.started_at else None,
                        task.completed_at.isoformat() if task.completed_at else None,
                    ),
                )
        return plan

    def get_plan(self, plan_id: str) -> tuple[PlanRecord, list[PlanTaskRecord]]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM plan WHERE plan_id=?", (plan_id,)).fetchone()
            tasks = connection.execute(
                "SELECT * FROM plan_task WHERE plan_id=? ORDER BY sequence_no", (plan_id,)
            ).fetchall()
        if row is None:
            raise FileNotFoundError(plan_id)
        return _plan(row), [_plan_task(item) for item in tasks]

    def update_plan_task(self, task: PlanTaskRecord) -> PlanTaskRecord:
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                """
                UPDATE plan_task SET status=?,started_at=?,completed_at=?
                WHERE task_id=? AND plan_id=?
                """,
                (
                    task.status.value,
                    task.started_at.isoformat() if task.started_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    task.task_id,
                    task.plan_id,
                ),
            ).rowcount
            if changed != 1:
                raise FileNotFoundError(task.task_id)
            connection.execute(
                "UPDATE plan SET version=version+1,updated_at=? WHERE plan_id=?",
                (_now(), task.plan_id),
            )
        return task

    def update_plan_status(self, plan_id: str, status: PlanStatus) -> PlanRecord:
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                "UPDATE plan SET status=?,version=version+1,updated_at=? WHERE plan_id=?",
                (status.value, _now(), plan_id),
            ).rowcount
            if changed != 1:
                raise FileNotFoundError(plan_id)
            row = connection.execute(
                "SELECT * FROM plan WHERE plan_id=?", (plan_id,)
            ).fetchone()
        assert row is not None
        return _plan(row)

    # Approvals, results and evidence ----------------------------------

    def save_approval(self, approval: ApprovalState) -> ApprovalState:
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO approval(
                    approval_id,run_id,session_id,tool_id,tool_version,schema_hash,arguments_json,
                    arguments_hash,idempotency_key,impact_summary,policy_reason,external_state_token,
                    run_revision,run_allowed_tools_json,skill_allowed_tools_json,status,
                    confirmations_required,confirmations_json,expires_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    approval.approval_id,
                    approval.run_id,
                    approval.session_id,
                    approval.tool_id,
                    approval.tool_version,
                    approval.schema_hash,
                    _json(approval.arguments),
                    approval.arguments_hash,
                    approval.idempotency_key,
                    approval.impact_summary,
                    approval.policy_reason,
                    approval.external_state_token,
                    approval.run_revision,
                    _json(approval.run_allowed_tools),
                    _json(approval.skill_allowed_tools),
                    approval.status,
                    approval.confirmations_required,
                    _json(approval.confirmations),
                    approval.expires_at.isoformat(),
                    approval.created_at.isoformat(),
                ),
            )
        return approval

    def get_approval(self, approval_id: str) -> ApprovalState:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM approval WHERE approval_id=?", (approval_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(approval_id)
        return _approval(row)

    def list_approvals(self, run_id: str) -> list[ApprovalState]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM approval WHERE run_id=? ORDER BY created_at", (run_id,)
            ).fetchall()
        return [_approval(row) for row in rows]

    def update_approval(self, approval: ApprovalState, expected_status: str) -> ApprovalState:
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                """
                UPDATE approval SET status=?,confirmations_json=?,external_state_token=?,expires_at=?
                WHERE approval_id=? AND status=?
                """,
                (
                    approval.status,
                    _json(approval.confirmations),
                    approval.external_state_token,
                    approval.expires_at.isoformat(),
                    approval.approval_id,
                    expected_status,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("stale approval")
        return approval

    def put_tool_result(
        self,
        *,
        session_id: str,
        run_id: str,
        tool_id: str,
        tool_version: str,
        status: str,
        digest: object,
        raw_payload: object | None,
        external_ref: str | None = None,
    ) -> str:
        result_id = str(uuid4())
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO tool_result(
                    result_id,session_id,run_id,tool_id,tool_version,status,digest_json,
                    raw_payload_json,external_ref,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    result_id,
                    session_id,
                    run_id,
                    tool_id,
                    tool_version,
                    status,
                    _json(digest),
                    _json(raw_payload) if raw_payload is not None else None,
                    external_ref,
                    _now(),
                ),
            )
        return result_id

    def get_tool_result(
        self, result_id: str, *, session_id: str | None = None
    ) -> dict[str, object]:
        clauses = ["result_id=?"]
        values: list[object] = [result_id]
        if session_id is not None:
            clauses.append("session_id=?")
            values.append(session_id)
        with self.transaction() as connection:
            row = connection.execute(
                f"SELECT * FROM tool_result WHERE {' AND '.join(clauses)}", values
            ).fetchone()
        if row is None:
            raise FileNotFoundError(result_id)
        return {
            "result_id": row["result_id"],
            "session_id": row["session_id"],
            "run_id": row["run_id"],
            "tool_id": row["tool_id"],
            "tool_version": row["tool_version"],
            "status": row["status"],
            "digest": json.loads(row["digest_json"]),
            "raw_payload": json.loads(row["raw_payload_json"])
            if row["raw_payload_json"] is not None
            else None,
            "external_ref": row["external_ref"],
            "created_at": row["created_at"],
        }

    def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO evidence(
                    evidence_id,session_id,run_id,source_type,source_ref,content_digest,validity,
                    observed_at,expires_at,recall_event_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    evidence.evidence_id,
                    evidence.session_id,
                    evidence.run_id,
                    evidence.source_type,
                    evidence.source_ref,
                    evidence.content_digest,
                    evidence.validity,
                    evidence.observed_at.isoformat() if evidence.observed_at else None,
                    evidence.expires_at.isoformat() if evidence.expires_at else None,
                    evidence.recall_event_id,
                    evidence.created_at.isoformat(),
                ),
            )
        return evidence

    def get_evidence(self, evidence_id: str, *, session_id: str) -> EvidenceRecord:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM evidence WHERE evidence_id=? AND session_id=?",
                (evidence_id, session_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(evidence_id)
        return EvidenceRecord.model_validate(dict(row))

    def save_evidence_usage(self, usage: EvidenceUsage) -> EvidenceUsage:
        with self.transaction(write=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM evidence WHERE evidence_id=? AND session_id=?",
                (usage.evidence_id, usage.session_id),
            ).fetchone()
            if exists is None:
                raise ValueError("unknown evidence")
            connection.execute(
                """
                INSERT INTO evidence_usage(
                    usage_id,session_id,run_id,evidence_id,derived_fact,usage_type,
                    future_relevant,event_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    usage.usage_id,
                    usage.session_id,
                    usage.run_id,
                    usage.evidence_id,
                    usage.derived_fact,
                    usage.usage_type,
                    int(usage.future_relevant),
                    usage.event_id,
                    usage.created_at.isoformat(),
                ),
            )
        return usage

    def evidence_usage(self, session_id: str) -> list[EvidenceUsage]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_usage WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [_evidence_usage(row) for row in rows]

    # Versioned capabilities and FTS -----------------------------------

    def sync_skill_definition(
        self,
        *,
        skill_id: str,
        version: str,
        name: str,
        description: str,
        body: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        content_hash = hashlib.sha256(body.encode()).hexdigest()
        row_key = f"{skill_id}@{version}"
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO skill_definition(
                    row_key,skill_id,version,name,description,body,content_hash,
                    estimated_tokens,metadata_json,is_enabled,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(row_key) DO UPDATE SET
                    name=excluded.name,description=excluded.description,body=excluded.body,
                    content_hash=excluded.content_hash,estimated_tokens=excluded.estimated_tokens,
                    metadata_json=excluded.metadata_json,is_enabled=1
                """,
                (
                    row_key,
                    skill_id,
                    version,
                    name,
                    description,
                    body,
                    content_hash,
                    _estimate_tokens(body),
                    _json(metadata or {}),
                    _now(),
                ),
            )
        return content_hash

    def get_skill_definition(self, skill_id: str, version: str) -> dict[str, object]:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM skill_definition WHERE skill_id=? AND version=? AND is_enabled=1",
                (skill_id, version),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"{skill_id}@{version}")
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def sync_tool_definition(
        self,
        *,
        tool_id: str,
        version: str,
        name: str,
        description: str,
        namespace: str,
        input_schema: dict[str, object],
        aliases: Sequence[str] = (),
        metadata: dict[str, object] | None = None,
    ) -> str:
        schema_text = _json(input_schema)
        schema_hash = hashlib.sha256(schema_text.encode()).hexdigest()
        search_text = " ".join(
            [name, description, namespace, *aliases, schema_text]
        )
        row_key = f"{tool_id}@{version}"
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO tool_definition(
                    row_key,tool_id,version,name,description,namespace,input_schema_json,aliases_json,
                    metadata_json,schema_hash,is_enabled,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(row_key) DO UPDATE SET
                    name=excluded.name,description=excluded.description,namespace=excluded.namespace,
                    input_schema_json=excluded.input_schema_json,aliases_json=excluded.aliases_json,
                    metadata_json=excluded.metadata_json,schema_hash=excluded.schema_hash,is_enabled=1
                """,
                (
                    row_key,
                    tool_id,
                    version,
                    name,
                    description,
                    namespace,
                    schema_text,
                    _json(list(aliases)),
                    _json(metadata or {}),
                    schema_hash,
                    _now(),
                ),
            )
            connection.execute("DELETE FROM tool_definition_fts WHERE row_key=?", (row_key,))
            connection.execute(
                "INSERT INTO tool_definition_fts(row_key,search_text) VALUES(?,?)",
                (row_key, search_text),
            )
        return schema_hash

    def search_tools(
        self,
        query: str,
        *,
        namespace: str | None = None,
        capability_kind: str | None = None,
        allowed_tool_ids: Sequence[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        top_k = max(1, min(top_k, 10))
        terms = [term for term in re.findall(r"[\w\-]+", query, flags=re.UNICODE) if term]
        if not terms:
            return []
        match = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
        conditions = ["tool_definition_fts MATCH ?", "d.is_enabled=1"]
        values: list[object] = [match]
        if namespace:
            conditions.append("d.namespace=?")
            values.append(namespace)
        if capability_kind:
            conditions.append("json_extract(d.metadata_json, '$.kind')=?")
            values.append(capability_kind)
        if allowed_tool_ids is not None:
            allowed = sorted({str(tool_id) for tool_id in allowed_tool_ids})
            if not allowed:
                return []
            conditions.append(f"d.tool_id IN ({','.join('?' for _ in allowed)})")
            values.extend(allowed)
        with self.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT d.*,bm25(tool_definition_fts) AS score
                FROM tool_definition_fts
                JOIN tool_definition d USING(row_key)
                WHERE {' AND '.join(conditions)}
                ORDER BY
                    CASE WHEN lower(d.name)=lower(?) THEN 0 ELSE 1 END,
                    score
                LIMIT ?
                """,
                [*values, query, top_k],
            ).fetchall()
        return [
            {
                "tool_id": row["tool_id"],
                "version": row["version"],
                "name": row["name"],
                "description": row["description"],
                "namespace": row["namespace"],
                "schema_hash": row["schema_hash"],
                "score": float(row["score"]),
            }
            for row in rows
        ]

    # Local knowledge and memory --------------------------------------

    def add_knowledge_document(
        self, *, title: str, content: str, media_type: str = "text/plain"
    ) -> str:
        document_id = str(uuid4())
        chunks = _chunk_text(content)
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_document(document_id,title,media_type,content_hash,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    document_id,
                    title,
                    media_type,
                    hashlib.sha256(content.encode()).hexdigest(),
                    _now(),
                ),
            )
            for index, chunk in enumerate(chunks):
                chunk_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO knowledge_chunk(chunk_id,document_id,sequence_no,content,token_count)
                    VALUES(?,?,?,?,?)
                    """,
                    (chunk_id, document_id, index, chunk, _estimate_tokens(chunk)),
                )
                connection.execute(
                    "INSERT INTO knowledge_chunk_fts(chunk_id,title,content) VALUES(?,?,?)",
                    (chunk_id, title, chunk),
                )
        return document_id

    def list_knowledge_documents(self) -> list[dict[str, object]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_document ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_knowledge_document(self, document_id: str) -> bool:
        with self.transaction(write=True) as connection:
            chunk_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT chunk_id FROM knowledge_chunk WHERE document_id=?", (document_id,)
                ).fetchall()
            ]
            for chunk_id in chunk_ids:
                connection.execute(
                    "DELETE FROM knowledge_chunk_fts WHERE chunk_id=?", (chunk_id,)
                )
            return connection.execute(
                "DELETE FROM knowledge_document WHERE document_id=?", (document_id,)
            ).rowcount == 1

    def search_knowledge(
        self, query: str, *, max_chunks: int = 5, max_tokens: int = 4000
    ) -> list[dict[str, object]]:
        match = _fts_query(query)
        if not match:
            return []
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT c.*,d.title,bm25(knowledge_chunk_fts) AS score
                FROM knowledge_chunk_fts
                JOIN knowledge_chunk c USING(chunk_id)
                JOIN knowledge_document d USING(document_id)
                WHERE knowledge_chunk_fts MATCH ?
                ORDER BY score LIMIT ?
                """,
                (match, max(1, min(max_chunks * 3, 30))),
            ).fetchall()
        selected: list[dict[str, object]] = []
        used = 0
        for row in rows:
            tokens = int(row["token_count"])
            if selected and used + tokens > max_tokens:
                continue
            selected.append(
                {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "content": row["content"],
                    "token_count": tokens,
                    "score": float(row["score"]),
                }
            )
            used += tokens
            if len(selected) >= max_chunks:
                break
        return selected

    def add_memory(self, *, content: str, source: str = "user") -> str:
        memory_id = str(uuid4())
        with self.transaction(write=True) as connection:
            connection.execute(
                "INSERT INTO memory_item(memory_id,content,source,created_at,updated_at) VALUES(?,?,?,?,?)",
                (memory_id, content, source, _now(), _now()),
            )
            connection.execute(
                "INSERT INTO memory_item_fts(memory_id,content) VALUES(?,?)",
                (memory_id, content),
            )
        return memory_id

    def list_memories(self) -> list[dict[str, object]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_item ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_memory(self, memory_id: str) -> bool:
        with self.transaction(write=True) as connection:
            connection.execute("DELETE FROM memory_item_fts WHERE memory_id=?", (memory_id,))
            return connection.execute(
                "DELETE FROM memory_item WHERE memory_id=?", (memory_id,)
            ).rowcount == 1

    def search_memories(self, query: str, *, limit: int = 5) -> list[dict[str, object]]:
        match = _fts_query(query)
        if not match:
            return []
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT m.*,bm25(memory_item_fts) AS score
                FROM memory_item_fts JOIN memory_item m USING(memory_id)
                WHERE memory_item_fts MATCH ? ORDER BY score LIMIT ?
                """,
                (match, max(1, min(limit, 20))),
            ).fetchall()
        return [dict(row) for row in rows]

    # Model-turn manifests ---------------------------------------------

    def save_context_manifest(self, manifest: ContextManifest) -> ContextManifest:
        with self.transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO model_turn(
                    turn_id,session_id,run_id,checkpoint_id,first_event_sequence,last_event_sequence,
                    prefix_hash,model_profile_id,tool_versions_json,skill_versions_json,
                    evidence_ids_json,token_breakdown_json,estimated_prompt_tokens,actual_usage_json,
                    context_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    manifest.turn_id,
                    manifest.session_id,
                    manifest.run_id,
                    manifest.checkpoint_id,
                    manifest.first_event_sequence,
                    manifest.last_event_sequence,
                    manifest.prefix_hash,
                    manifest.model_profile_id,
                    _json(manifest.tool_versions),
                    _json(manifest.skill_versions),
                    _json(manifest.evidence_ids),
                    _json(manifest.token_breakdown),
                    manifest.estimated_prompt_tokens,
                    _json(manifest.actual_usage),
                    manifest.context_hash,
                    manifest.created_at.isoformat(),
                ),
            )
        return manifest

    def update_context_usage(
        self, turn_id: str, usage: dict[str, int]
    ) -> ContextManifest:
        with self.transaction(write=True) as connection:
            changed = connection.execute(
                "UPDATE model_turn SET actual_usage_json=? WHERE turn_id=?",
                (_json(usage), turn_id),
            ).rowcount
            if changed != 1:
                raise FileNotFoundError(turn_id)
            row = connection.execute(
                "SELECT * FROM model_turn WHERE turn_id=?", (turn_id,)
            ).fetchone()
        assert row is not None
        return _manifest(row)

    def list_context_manifests(self, session_id: str) -> list[ContextManifest]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM model_turn WHERE session_id=? ORDER BY created_at", (session_id,)
            ).fetchall()
        return [_manifest(row) for row in rows]


def _session(row: sqlite3.Row) -> AgentSession:
    return AgentSession.model_validate(dict(row))


def _run(row: sqlite3.Row) -> AgentRun:
    values = dict(row)
    values["requested_skills"] = json.loads(values.pop("requested_skills_json"))
    values["input_artifact_ids"] = json.loads(values.pop("input_artifact_ids_json"))
    values["active_skill_versions"] = json.loads(values.pop("active_skill_versions_json"))
    values["active_tool_versions"] = json.loads(values.pop("active_tool_versions_json"))
    values["working_state"] = json.loads(values.pop("working_state_json"))
    return AgentRun.model_validate(values)


def _event(row: sqlite3.Row) -> AgentEvent:
    return AgentEvent(
        event_id=row["event_id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        sequence=row["sequence_no"],
        event_type=row["event_type"],
        payload=json.loads(row["payload_json"]),
        metadata=json.loads(row["metadata_json"]),
        references=json.loads(row["references_json"]),
        token_count=row["token_count"],
        created_at=row["created_at"],
    )


def _checkpoint(row: sqlite3.Row) -> CheckpointRecord:
    return CheckpointRecord(
        checkpoint_id=row["checkpoint_id"],
        session_id=row["session_id"],
        parent_checkpoint_id=row["parent_checkpoint_id"],
        generation=row["generation"],
        covered_until_sequence=row["covered_until_sequence"],
        state=json.loads(row["state_json"]),
        token_count=row["token_count"],
        build_type=row["build_type"],
        created_at=row["created_at"],
    )


def _plan(row: sqlite3.Row) -> PlanRecord:
    return PlanRecord.model_validate(dict(row))


def _plan_task(row: sqlite3.Row) -> PlanTaskRecord:
    values = dict(row)
    values["sequence"] = values.pop("sequence_no")
    values["depends_on"] = json.loads(values.pop("depends_on_json"))
    return PlanTaskRecord.model_validate(values)


def _approval(row: sqlite3.Row) -> ApprovalState:
    values = dict(row)
    values["arguments"] = json.loads(values.pop("arguments_json"))
    values["run_allowed_tools"] = json.loads(values.pop("run_allowed_tools_json"))
    values["skill_allowed_tools"] = json.loads(values.pop("skill_allowed_tools_json"))
    values["confirmations"] = json.loads(values.pop("confirmations_json"))
    return ApprovalState.model_validate(values)


def _evidence_usage(row: sqlite3.Row) -> EvidenceUsage:
    values = dict(row)
    values["future_relevant"] = bool(values["future_relevant"])
    return EvidenceUsage.model_validate(values)


def _manifest(row: sqlite3.Row) -> ContextManifest:
    values = dict(row)
    for key in (
        "tool_versions",
        "skill_versions",
        "evidence_ids",
        "token_breakdown",
        "actual_usage",
    ):
        values[key] = json.loads(values.pop(f"{key}_json"))
    return ContextManifest.model_validate(values)


def _validate_plan_tasks(tasks: Sequence[PlanTaskRecord]) -> None:
    if len(tasks) > 50:
        raise ValueError("a plan may contain at most 50 tasks")
    identifiers = {task.task_id for task in tasks}
    if len(identifiers) != len(tasks):
        raise ValueError("duplicate plan task")
    if any(dependency not in identifiers for task in tasks for dependency in task.depends_on):
        raise ValueError("unknown plan dependency")
    graph = {task.task_id: set(task.depends_on) for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError("plan dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for identifier in graph:
        visit(identifier)


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 2) // 3)


def _chunk_text(content: str, *, target_tokens: int = 800, overlap_tokens: int = 100) -> list[str]:
    target_chars = target_tokens * 3
    overlap_chars = overlap_tokens * 3
    normalized = content.strip()
    if not normalized:
        raise ValueError("knowledge document is empty")
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + target_chars)
        if end < len(normalized):
            boundary = max(normalized.rfind("\n", start, end), normalized.rfind("。", start, end))
            if boundary > start + target_chars // 2:
                end = boundary + 1
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


def _fts_query(query: str) -> str:
    terms = [term for term in re.findall(r"[\w\-]+", query, flags=re.UNICODE) if term]
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)


_SCHEMA_V1 = """
CREATE TABLE agent_session (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_definition_version TEXT NOT NULL,
    prefix_text TEXT NOT NULL,
    prefix_hash TEXT NOT NULL,
    capability_index_hash TEXT NOT NULL,
    model_profile_id TEXT NOT NULL,
    status TEXT NOT NULL,
    active_run_id TEXT,
    next_event_sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_run (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    parent_run_id TEXT REFERENCES agent_run(run_id) ON DELETE SET NULL,
    objective TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    requested_skills_json TEXT NOT NULL,
    input_artifact_ids_json TEXT NOT NULL,
    active_skill_versions_json TEXT NOT NULL,
    active_tool_versions_json TEXT NOT NULL,
    consumed_steps INTEGER NOT NULL,
    max_steps INTEGER NOT NULL,
    max_seconds INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    current_plan_id TEXT,
    pending_approval_id TEXT,
    final_text TEXT,
    error_code TEXT,
    working_state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_agent_run_session ON agent_run(session_id,created_at);

CREATE TABLE agent_event (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES agent_run(run_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    references_json TEXT NOT NULL,
    token_count INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(session_id,sequence_no)
);
CREATE INDEX idx_agent_event_session_seq ON agent_event(session_id,sequence_no);
CREATE INDEX idx_agent_event_run_seq ON agent_event(run_id,sequence_no);
CREATE INDEX idx_agent_event_type ON agent_event(event_type);

CREATE TABLE session_checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    parent_checkpoint_id TEXT REFERENCES session_checkpoint(checkpoint_id),
    generation INTEGER NOT NULL,
    covered_until_sequence INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    token_count INTEGER,
    build_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id,generation)
);

CREATE TABLE plan (
    plan_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_run(run_id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE plan_task (
    task_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plan(plan_id) ON DELETE CASCADE,
    parent_task_id TEXT REFERENCES plan_task(task_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    depends_on_json TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE approval (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_run(run_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    tool_id TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    arguments_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    impact_summary TEXT NOT NULL,
    policy_reason TEXT NOT NULL,
    external_state_token TEXT,
    run_revision INTEGER NOT NULL,
    run_allowed_tools_json TEXT,
    skill_allowed_tools_json TEXT,
    status TEXT NOT NULL,
    confirmations_required INTEGER NOT NULL,
    confirmations_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE tool_definition (
    row_key TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    namespace TEXT NOT NULL,
    input_schema_json TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    is_enabled INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(tool_id,version)
);
CREATE VIRTUAL TABLE tool_definition_fts USING fts5(row_key UNINDEXED,search_text);

CREATE TABLE skill_definition (
    row_key TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    is_enabled INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(skill_id,version)
);

CREATE TABLE tool_result (
    result_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_run(run_id) ON DELETE CASCADE,
    tool_id TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    status TEXT NOT NULL,
    digest_json TEXT NOT NULL,
    raw_payload_json TEXT,
    external_ref TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES agent_run(run_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    validity TEXT NOT NULL,
    observed_at TEXT,
    expires_at TEXT,
    recall_event_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE evidence_usage (
    usage_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES agent_run(run_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
    derived_fact TEXT NOT NULL,
    usage_type TEXT NOT NULL,
    future_relevant INTEGER NOT NULL,
    event_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_document (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    media_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE knowledge_chunk (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES knowledge_document(document_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL
);
CREATE VIRTUAL TABLE knowledge_chunk_fts USING fts5(chunk_id UNINDEXED,title,content);

CREATE TABLE memory_item (
    memory_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE memory_item_fts USING fts5(memory_id UNINDEXED,content);

CREATE TABLE model_turn (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_session(session_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_run(run_id) ON DELETE CASCADE,
    checkpoint_id TEXT,
    first_event_sequence INTEGER,
    last_event_sequence INTEGER,
    prefix_hash TEXT NOT NULL,
    model_profile_id TEXT NOT NULL,
    tool_versions_json TEXT NOT NULL,
    skill_versions_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    token_breakdown_json TEXT NOT NULL,
    estimated_prompt_tokens INTEGER NOT NULL,
    actual_usage_json TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
