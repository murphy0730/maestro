from fastapi.testclient import TestClient

from maestro.api.app import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    return TestClient(create_app())


def test_create_run_returns_identity(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/runs", json={"session_id": "s1", "message": "解释 OEE", "skill_names": []})
    assert response.status_code == 202
    assert response.json()["path"] in {"fast", "structured"}
    assert response.json()["run_id"]


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
