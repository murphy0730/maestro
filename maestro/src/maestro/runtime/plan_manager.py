"""Generic persisted plan projection for controlled agent runs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.trajectory import (
    AgentRun,
    PlanRecord,
    PlanStatus,
    PlanTaskRecord,
    PlanTaskStatus,
)


class PlanManager:
    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def create_default(self, run: AgentRun) -> tuple[PlanRecord, list[PlanTaskRecord]]:
        plan = PlanRecord(session_id=run.session_id, run_id=run.run_id, goal=run.objective)
        task_specs = (
            [
                ("Apply the selected skill to the objective", []),
                ("Verify the result and report remaining uncertainty", ["first"]),
            ]
            if run.requested_skills
            else [
                ("Resolve the objective using verified information", []),
                ("Verify the result and report remaining uncertainty", ["first"]),
            ]
        )
        first_id = str(uuid4())
        verify_id = str(uuid4())
        tasks = [
            PlanTaskRecord(
                task_id=first_id if index == 0 else verify_id,
                plan_id=plan.plan_id,
                title=title,
                sequence=index,
                depends_on=[] if index == 0 else [first_id],
                status=PlanTaskStatus.READY if index == 0 else PlanTaskStatus.PENDING,
            )
            for index, (title, _dependencies) in enumerate(task_specs)
        ]
        self._store.create_plan(plan, tasks)
        return plan, tasks

    def current(self, plan_id: str) -> PlanTaskRecord | None:
        _, tasks = self._store.get_plan(plan_id)
        return next(
            (
                task
                for task in tasks
                if task.status in {PlanTaskStatus.IN_PROGRESS, PlanTaskStatus.READY}
            ),
            None,
        )

    def start(self, task: PlanTaskRecord) -> PlanTaskRecord:
        if task.status not in {PlanTaskStatus.READY, PlanTaskStatus.PENDING}:
            return task
        _, tasks = self._store.get_plan(task.plan_id)
        completed = {
            item.task_id for item in tasks if item.status is PlanTaskStatus.COMPLETED
        }
        if any(identifier not in completed for identifier in task.depends_on):
            raise ValueError("plan task dependencies are not complete")
        return self._store.update_plan_task(
            task.model_copy(
                update={
                    "status": PlanTaskStatus.IN_PROGRESS,
                    "started_at": datetime.now(UTC),
                }
            )
        )

    def complete(self, task: PlanTaskRecord) -> tuple[PlanTaskRecord, PlanTaskRecord | None]:
        completed = self._store.update_plan_task(
            task.model_copy(
                update={
                    "status": PlanTaskStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                }
            )
        )
        _, tasks = self._store.get_plan(task.plan_id)
        done = {item.task_id for item in tasks if item.status is PlanTaskStatus.COMPLETED}
        next_task = next(
            (
                item
                for item in tasks
                if item.status is PlanTaskStatus.PENDING
                and all(dependency in done for dependency in item.depends_on)
            ),
            None,
        )
        if next_task is not None:
            next_task = self._store.update_plan_task(
                next_task.model_copy(update={"status": PlanTaskStatus.READY})
            )
        return completed, next_task

    def complete_all(self, plan_id: str) -> list[PlanTaskRecord]:
        """Close a generic plan after the Runtime has accepted a final answer."""
        _plan, tasks = self._store.get_plan(plan_id)
        completed: list[PlanTaskRecord] = []
        now = datetime.now(UTC)
        for task in tasks:
            if task.status in {
                PlanTaskStatus.COMPLETED,
                PlanTaskStatus.FAILED,
                PlanTaskStatus.SKIPPED,
            }:
                completed.append(task)
                continue
            completed.append(
                self._store.update_plan_task(
                    task.model_copy(
                        update={
                            "status": PlanTaskStatus.COMPLETED,
                            "started_at": task.started_at or now,
                            "completed_at": now,
                        }
                    )
                )
            )
        self._store.update_plan_status(plan_id, PlanStatus.COMPLETED)
        return completed
