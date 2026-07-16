import json

import pytest

from maestro.runtime.journal import (
    JournalCorruption,
    JournalEvent,
    JsonlJournal,
    replay_run,
)
from maestro.runtime.models import RunPath, RunRecord, RunStatus


def test_journal_survives_new_instance(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    JsonlJournal(path).append(
        JournalEvent(run_id="r1", type="run.created", data={"objective": "x"})
    )

    assert [event.type for event in JsonlJournal(path).read("r1")] == ["run.created"]


def test_journal_rejects_malformed_lines(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(JournalCorruption, match="line 1"):
        JsonlJournal(path).read("r1")


def test_journal_rejects_lines_with_unknown_fields(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text(
        '{"run_id":"r1","type":"run.created","unexpected":true}\n',
        encoding="utf-8",
    )

    with pytest.raises(JournalCorruption, match="line 1"):
        JsonlJournal(path).read("r1")


def test_journal_replay_is_deterministic(tmp_path) -> None:
    journal = JsonlJournal(tmp_path / "journal.jsonl")
    journal.append(JournalEvent(run_id="r1", type="run.created", data={"objective": "x"}))
    journal.append(
        JournalEvent(run_id="r1", type="run.path_selected", data={"path": "fast"})
    )
    journal.append(
        JournalEvent(run_id="r1", type="run.completed", data={"final_text": "done"})
    )

    first = replay_run(journal.read("r1"))
    second = replay_run(journal.read("r1"))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.run_id == "r1"
    assert first.objective == "x"
    assert first.path is RunPath.FAST
    assert first.status is RunStatus.COMPLETED
    assert first.final_text == "done"


def test_replay_rejects_non_continuous_sequences() -> None:
    events = [
        JournalEvent(
            run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
        ),
        JournalEvent(run_id="r1", sequence=2, type="run.completed"),
    ]

    with pytest.raises(ValueError, match="continuous"):
        replay_run(events)


def test_replay_rejects_unknown_events() -> None:
    events = [
        JournalEvent(
            run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
        ),
        JournalEvent(run_id="r1", sequence=1, type="run.unknown"),
    ]

    with pytest.raises(ValueError, match="unknown"):
        replay_run(events)


def test_replay_rebuilds_controlled_failure_and_rejects_later_events() -> None:
    artifact = {
        "artifact_id": "a" * 64,
        "sha256": "a" * 64,
        "media_type": "application/json",
        "bytes": 1,
    }
    events = [
        JournalEvent(run_id="r1", sequence=0, type="run.created", data={"objective": "x"}),
        JournalEvent(run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}),
        JournalEvent(
            run_id="r1",
            sequence=2,
            type="run.path_upgraded",
            data={"reason": "high_risk_write", "artifact_working_set": [artifact]},
        ),
        JournalEvent(
            run_id="r1",
            sequence=3,
            type="run.failed",
            data={"reason": "controlled_budget_exhausted"},
        ),
    ]

    failed = replay_run(events)

    assert failed.status is RunStatus.FAILED
    with pytest.raises(ValueError, match="run.completed requires an active run"):
        replay_run(events + [JournalEvent(run_id="r1", sequence=4, type="run.completed")])


def test_replay_applies_ordered_controlled_execution_upgrade() -> None:
    artifact_working_set = [
        {
            "artifact_id": "a" * 64,
            "sha256": "a" * 64,
            "media_type": "application/json",
            "bytes": 12,
        }
    ]
    events = [
        JournalEvent(
            run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
        ),
        JournalEvent(
            run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
        ),
        JournalEvent(
            run_id="r1",
            sequence=2,
            type="run.upgrading",
            data={
                "reason": "skill_upgrade_required",
                "artifact_working_set": artifact_working_set,
            },
        ),
        JournalEvent(
            run_id="r1",
            sequence=3,
            type="run.upgraded",
            data={
                "reason": "skill_upgrade_required",
                "artifact_working_set": artifact_working_set,
            },
        ),
    ]

    structuring = replay_run(events[:-1])
    replayed = replay_run(events)

    assert structuring.status is RunStatus.STRUCTURING
    assert replayed.path is RunPath.STRUCTURED
    assert replayed.status is RunStatus.RUNNING_STRUCTURED


@pytest.mark.parametrize(
    ("path", "status"),
    [
        (RunPath.FAST.value, RunStatus.RUNNING_FAST),
        (RunPath.STRUCTURED.value, RunStatus.STRUCTURING),
    ],
)
def test_replay_path_selection_enters_matching_state(path: str, status: RunStatus) -> None:
    replayed = replay_run(
        [
            JournalEvent(
                run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
            ),
            JournalEvent(
                run_id="r1", sequence=1, type="run.path_selected", data={"path": path}
            ),
        ]
    )

    assert replayed.status is status


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (
            [
                JournalEvent(
                    run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=1,
                    type="run.upgraded",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
            ],
            "run.upgraded requires run.upgrading",
        ),
        (
            [
                JournalEvent(
                    run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
                ),
                JournalEvent(
                    run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=2,
                    type="run.upgrading",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=3,
                    type="run.upgraded",
                    data={"reason": "other", "artifact_working_set": []},
                ),
            ],
            "run.upgraded must preserve upgrade data",
        ),
        (
            [
                JournalEvent(
                    run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
                ),
                JournalEvent(
                    run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
                ),
                JournalEvent(run_id="r1", sequence=2, type="run.completed"),
                JournalEvent(
                    run_id="r1",
                    sequence=3,
                    type="run.upgrading",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
            ],
            "run.upgrading requires a fast run",
        ),
        (
            [
                JournalEvent(
                    run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
                ),
                JournalEvent(
                    run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=2,
                    type="run.upgrading",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
                JournalEvent(run_id="r1", sequence=3, type="run.completed"),
            ],
            "run.completed cannot interrupt upgrade",
        ),
        (
            [
                JournalEvent(
                    run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
                ),
                JournalEvent(
                    run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=2,
                    type="run.upgrading",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
                JournalEvent(
                    run_id="r1", sequence=3, type="run.path_selected", data={"path": "fast"}
                ),
                JournalEvent(
                    run_id="r1",
                    sequence=4,
                    type="run.upgraded",
                    data={"reason": "skill_upgrade_required", "artifact_working_set": []},
                ),
            ],
            "run.path_selected requires an unselected run",
        ),
    ],
)
def test_replay_rejects_illegal_controlled_execution_upgrade_order(
    events: list[JournalEvent], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replay_run(events)


@pytest.mark.parametrize(
    "artifact",
    [
        {
            "artifact_id": "b" * 64,
            "sha256": "a" * 64,
            "media_type": "application/json",
            "bytes": 1,
        },
        {
            "artifact_id": "a" * 64,
            "sha256": "not-a-hash",
            "media_type": "application/json",
            "bytes": 1,
        },
        {
            "artifact_id": "a" * 64,
            "sha256": "a" * 64,
            "media_type": "application/json",
            "bytes": -1,
        },
    ],
)
def test_replay_rejects_non_reproducible_upgrade_artifact(artifact: dict[str, object]) -> None:
    events = [
        JournalEvent(
            run_id="r1", sequence=0, type="run.created", data={"objective": "x"}
        ),
        JournalEvent(
            run_id="r1", sequence=1, type="run.path_selected", data={"path": "fast"}
        ),
        JournalEvent(
            run_id="r1",
            sequence=2,
            type="run.upgrading",
            data={"reason": "skill_upgrade_required", "artifact_working_set": [artifact]},
        ),
    ]

    with pytest.raises(ValueError, match="valid artifact references"):
        replay_run(events)


def test_journal_preserves_append_order_not_event_timestamps(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    first = JournalEvent(run_id="r1", type="run.created", data={"objective": "x"})
    second = JournalEvent(run_id="r1", type="run.completed")
    path.write_text(
        "\n".join(
            [
                json.dumps(second.model_dump(mode="json")),
                json.dumps(first.model_dump(mode="json")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert [event.type for event in JsonlJournal(path).read("r1")] == [
        "run.completed",
        "run.created",
    ]


def test_replay_rejects_snapshot_on_non_published_event() -> None:
    run = RunRecord(run_id="r1", objective="x")
    with pytest.raises(ValueError, match="cannot contain a run snapshot"):
        replay_run([
            JournalEvent(run_id="r1", sequence=0, type="run.created", data={"objective": "x"}),
            JournalEvent(run_id="r1", sequence=1, type="model.turn", data={"run_snapshot": run.model_dump(mode="json")}),
        ])


def test_replay_rejects_snapshot_with_skipped_revision() -> None:
    created = RunRecord(run_id="r1", objective="x")
    running = created.model_copy(update={"path": RunPath.FAST, "status": RunStatus.RUNNING_FAST, "revision": 1})
    completed = running.model_copy(update={"status": RunStatus.COMPLETED, "revision": 3})
    with pytest.raises(ValueError, match="revision"):
        replay_run([
            JournalEvent(run_id="r1", sequence=0, type="run.created", data={"run_snapshot": created.model_dump(mode="json"), "snapshot_revision": 0}),
            JournalEvent(run_id="r1", sequence=1, type="run.path_selected", data={"run_snapshot": running.model_dump(mode="json"), "snapshot_revision": 1}),
            JournalEvent(run_id="r1", sequence=2, type="run.completed", data={"run_snapshot": completed.model_dump(mode="json"), "snapshot_revision": 3}),
        ])


def test_replay_restores_a_snapshot_from_the_last_non_state_event() -> None:
    created = RunRecord(run_id="r1", objective="x")
    running = created.model_copy(update={"path": RunPath.FAST, "status": RunStatus.RUNNING_FAST, "revision": 1})
    latest = running.model_copy(update={"consumed_steps": 1, "revision": 2})

    restored = replay_run([
        JournalEvent(run_id="r1", sequence=0, type="run.created", data={"run_snapshot": created.model_dump(mode="json"), "snapshot_revision": 0}),
        JournalEvent(run_id="r1", sequence=1, type="run.path_selected", data={"run_snapshot": running.model_dump(mode="json"), "snapshot_revision": 1}),
        JournalEvent(run_id="r1", sequence=2, type="capability.completed", data={"run_snapshot": latest.model_dump(mode="json"), "snapshot_revision": 2}),
    ])

    assert restored == latest
