import json

from maestro.foundation.session_store import SessionStore


def test_v3_session_rehydrates_messages_and_active_run(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("工作")
    store.append_message(session.session_id, "user", "hello", artifact_ids=["a"], skill_names=["reader"])
    store.set_active_run(session.session_id, "run-1")

    restored = SessionStore(tmp_path)
    assert restored.get(session.session_id).schema_version == 3
    assert restored.get(session.session_id).active_run_id == "run-1"
    assert restored.get_messages(session.session_id)[0]["artifact_ids"] == ["a"]


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
