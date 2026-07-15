import json

import pytest

from maestro.runtime.journal import (
    JournalCorruption,
    JournalEvent,
    JsonlJournal,
    replay_run,
)
from maestro.runtime.models import RunPath, RunStatus


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
        JournalEvent(run_id="r1", sequence=1, type="run.failed"),
    ]

    with pytest.raises(ValueError, match="unknown"):
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
