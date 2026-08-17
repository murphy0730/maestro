import json

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.foundation.session_store import SessionStore
from maestro.runtime.models import RunRecord, RunStatus
from maestro.runtime.store import RunStore


def test_v3_session_rehydrates_messages_and_active_run(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("工作")
    store.append_message(session.session_id, "user", "hello", artifact_ids=["a"], skill_names=["reader"])
    store.set_active_run(session.session_id, "run-1")

    restored = SessionStore(tmp_path)
    assert restored.get(session.session_id).schema_version == 3
    assert restored.get(session.session_id).active_run_id == "run-1"
    assert restored.get_messages(session.session_id)[0]["artifact_ids"] == ["a"]


def test_clearing_a_terminal_run_does_not_retire_a_newer_run(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    store.set_active_run(session.session_id, "old-run")
    store.set_active_run(session.session_id, "new-run")

    store.clear_active_run(session.session_id, "old-run")

    assert store.get(session.session_id).active_run_id == "new-run"
    store.clear_active_run(session.session_id, "new-run")
    assert store.get(session.session_id).active_run_id is None


def test_platform_startup_clears_a_stale_terminal_active_run(tmp_path) -> None:
    sessions_dir = tmp_path / "sessions"
    runs_dir = tmp_path / "runs"
    sessions = SessionStore(sessions_dir)
    session = sessions.create()
    terminal = RunRecord(
        run_id="finished-run",
        session_id=session.session_id,
        objective="done",
        status=RunStatus.COMPLETED,
    )
    RunStore(runs_dir).save(terminal)
    sessions.set_active_run(session.session_id, terminal.run_id)

    platform = build_platform(
        Settings(
            sessions_dir=sessions_dir,
            runs_dir=runs_dir,
            artifacts_dir=tmp_path / "artifacts",
            runtime_journal_file=tmp_path / "runtime" / "journal.jsonl",
            skills_dir=tmp_path / "skills",
            workspace_root=tmp_path / "workspace",
            summary_enabled=False,
        )
    )

    assert platform.session_store.get(session.session_id).active_run_id is None


def test_v2_index_is_ignored(tmp_path) -> None:
    (tmp_path / "index.json").write_text(json.dumps([{"session_id": "old", "engine": "query"}]))
    store = SessionStore(tmp_path)
    assert store.list_all() == []


def test_a_session_without_a_sidecar_has_no_summary(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()

    assert store.get_summary(session.session_id) == ("", 0)


def test_the_summary_sidecar_roundtrips_and_leaves_no_temporary(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()

    store.set_summary(session.session_id, "用户要查订单 SO-1", 12)

    assert SessionStore(tmp_path).get_summary(session.session_id) == ("用户要查订单 SO-1", 12)
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_corrupt_summary_sidecar_reads_as_absent(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    (tmp_path / f"{session.session_id}.summary.json").write_text("not json", "utf-8")

    assert store.get_summary(session.session_id) == ("", 0)


def test_the_summary_never_changes_the_messages_contract(tmp_path) -> None:
    """The frontend reads get_messages verbatim; summaries must stay in the sidecar."""
    store = SessionStore(tmp_path)
    session = store.create()
    store.append_message(session.session_id, "user", "hello")

    store.set_summary(session.session_id, "摘要", 1)

    assert [message["content"] for message in store.get_messages(session.session_id)] == ["hello"]


def test_deleting_a_session_removes_its_summary(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    store.set_summary(session.session_id, "摘要", 1)

    store.delete(session.session_id)

    assert not (tmp_path / f"{session.session_id}.summary.json").exists()
    assert store.get_summary(session.session_id) == ("", 0)


def test_deleting_one_message_updates_metadata_and_invalidates_summary(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    store.append_message(session.session_id, "user", "keep")
    store.append_message(session.session_id, "assistant", "delete me")
    store.set_summary(session.session_id, "stale summary", 2)
    target = store.get_messages(session.session_id)[1]["id"]

    assert store.delete_message(session.session_id, target) == [target]

    assert [message["content"] for message in store.get_messages(session.session_id)] == ["keep"]
    assert store.get(session.session_id).message_count == 1
    assert store.get_summary(session.session_id) == ("", 0)
    assert store.delete_message(session.session_id, "no-such-message") is None


def test_cascading_delete_removes_the_replies_of_that_turn_only(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    for role, content in [
        ("user", "第一问"),
        ("assistant", "第一答"),
        ("assistant", "补充"),
        ("user", "第二问"),
        ("assistant", "第二答"),
    ]:
        store.append_message(session.session_id, role, content)
    first_question = store.get_messages(session.session_id)[0]["id"]

    removed = store.delete_message(session.session_id, first_question, cascade=True)

    assert len(removed) == 3
    assert [message["content"] for message in store.get_messages(session.session_id)] == [
        "第二问",
        "第二答",
    ]


def test_cascading_delete_of_an_assistant_message_stays_single(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    store.append_message(session.session_id, "user", "问")
    store.append_message(session.session_id, "assistant", "答")
    reply = store.get_messages(session.session_id)[1]["id"]

    assert store.delete_message(session.session_id, reply, cascade=True) == [reply]
    assert [message["content"] for message in store.get_messages(session.session_id)] == ["问"]


def test_messages_stored_before_ids_existed_get_stable_ids_on_read(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create()
    legacy = [{"role": "user", "content": "旧消息", "ts": "2026-01-01T00:00:00+00:00"}]
    (tmp_path / f"{session.session_id}.json").write_text(json.dumps(legacy), "utf-8")

    first_read = store.get_messages(session.session_id)
    second_read = store.get_messages(session.session_id)

    assert first_read[0]["id"]
    assert first_read[0]["id"] == second_read[0]["id"]
    assert store.delete_message(session.session_id, first_read[0]["id"]) == [first_read[0]["id"]]


def test_migrating_a_legacy_session_does_not_clobber_a_concurrent_append(tmp_path, monkeypatch) -> None:
    """补 ID 要写回文件，写回的必须是当前内容，而不是读到时的那份旧快照。"""
    store = SessionStore(tmp_path)
    session = store.create()
    legacy = [{"role": "user", "content": "旧消息", "ts": "2026-01-01T00:00:00+00:00"}]
    (tmp_path / f"{session.session_id}.json").write_text(json.dumps(legacy), "utf-8")

    original = SessionStore._ensure_ids
    interleaved: list[bool] = []

    def append_between_read_and_write(messages: list[dict]) -> bool:
        assigned = original(messages)
        # 真实竞态就发生在「读完待迁移的旧文件」到「写回」之间的这个窗口里。
        if assigned and not interleaved:
            interleaved.append(True)
            store.append_message(session.session_id, "assistant", "新回复")
        return assigned

    monkeypatch.setattr(SessionStore, "_ensure_ids", staticmethod(append_between_read_and_write))
    store.get_messages(session.session_id)
    monkeypatch.undo()

    assert [message["content"] for message in store.get_messages(session.session_id)] == ["旧消息", "新回复"]
