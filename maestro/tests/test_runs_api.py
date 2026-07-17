from fastapi.testclient import TestClient
from datetime import UTC, datetime

from maestro.api.app import create_app
from maestro.runtime.events import RunEvent


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    return TestClient(create_app())


def test_create_run_returns_identity(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/runs", json={"session_id": "s1", "message": "解释 OEE", "skill_names": []})
    assert response.status_code == 202
    assert response.json()["path"] in {"fast", "structured"}
    assert response.json()["run_id"]
    assert response.json()["status"] in {"running_fast", "running_structured"}


def test_invalid_session_id_is_rejected_before_a_run_is_created(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/runs", json={"session_id": "../escape", "message": "hello"})
        assert response.status_code == 422
        assert list(client.app.state.platform.run_store.directory.glob("*.json")) == []


def test_event_source_creates_same_governed_run(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/runs", json={"session_id": "system-events", "message": "设备报警", "source": "event"})
    assert response.status_code == 202
    assert response.json()["intent"]["source"] == "event"


def test_artifact_round_trip_uses_opaque_id(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/artifacts", files={"file": ("input.txt", b"hello", "text/plain")})
        assert created.status_code == 201
        artifact_id = created.json()["artifact_id"]
        downloaded = client.get(f"/artifacts/{artifact_id}")
    assert downloaded.content == b"hello"
    assert "/" not in artifact_id


def test_run_persists_uploaded_artifacts_as_untrusted_runtime_context(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        artifact = client.post("/artifacts", files={"file": ("input.txt", b"hello", "text/plain")}).json()
        response = client.post("/runs", json={"message": "use attachment", "artifact_ids": [artifact["artifact_id"]]})
        stored = client.get(f"/runs/{response.json()['run_id']}").json()
    assert stored["input_artifact_ids"] == [artifact["artifact_id"]]


def test_runtime_skill_endpoints_are_available_without_msw(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        content = b"---\nname: local-skill\ndescription: local\n---\nDo work.\n"
        assert client.post("/skills/validate", files={"file": ("SKILL.md", content, "text/markdown")}).json()["compatible"]
        imported = client.post("/skills/import", files={"file": ("SKILL.md", content, "text/markdown")})
        assert imported.status_code == 200
        assert client.get("/skills").json()["skills"][0]["name"] == "local-skill"
        assert client.post("/skills/local-skill/trust", json={"trusted": True}).status_code == 200


def test_stream_replays_after_last_event_id(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/runs", json={"session_id": "s1", "message": "hello"})
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        response = client.get(f"/runs/{run_id}/stream")
    assert response.status_code == 200
    assert "event: run.completed" in response.text
    event_ids = [line.removeprefix("id: ") for line in response.text.splitlines() if line.startswith("id: ")]
    with _client(tmp_path, monkeypatch) as client:
        resumed = client.get(f"/runs/{run_id}/stream", headers={"Last-Event-ID": event_ids[0]})
    assert event_ids[0] not in resumed.text
    assert "event: run.completed" in resumed.text


def test_stream_projects_runtime_events_to_v1_names(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/runs", json={"message": "hello"})
        response = client.get(f"/runs/{created.json()['run_id']}/stream")
    assert "event: token.delta" in response.text


def test_stream_drains_event_published_after_history_before_terminal(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/runs", json={"message": "hello"})
        run_id = created.json()["run_id"]
        events = client.app.state.platform.runtime._events
        original_history = events.history

        def history_with_interleaving(identifier):
            history = original_history(identifier)
            events.publish(RunEvent(run_id=identifier, type="run.completed", data={"late": True}, occurred_at=datetime.now(UTC)))
            return history

        events.history = history_with_interleaving
        response = client.get(f"/runs/{run_id}/stream")
    assert '"late": true' in response.text


def test_stream_projects_failed_steps_and_approval_outcomes(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/runs", json={"message": "hello"})
        run_id = created.json()["run_id"]
        events = client.app.state.platform.runtime._events
        now = datetime.now(UTC)
        events.history = lambda _identifier: [
            RunEvent(run_id=run_id, type="capability.completed", data={"status": "failed"}, occurred_at=now),
            RunEvent(run_id=run_id, type="approval.expired", data={}, occurred_at=now),
            RunEvent(run_id=run_id, type="approval.resolved", data={}, occurred_at=now),
        ]
        response = client.get(f"/runs/{run_id}/stream")
    assert "event: step.failed" in response.text
    assert "event: approval.expired" in response.text
    assert "event: approval.resolved" in response.text
