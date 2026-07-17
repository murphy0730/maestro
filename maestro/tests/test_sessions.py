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
