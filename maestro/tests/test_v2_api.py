from __future__ import annotations

import time
from collections import deque

from fastapi.testclient import TestClient

from maestro.api.app import create_app
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.model import ModelAction


class FakeRuntimeModel:
    def __init__(self) -> None:
        self.actions: deque[ModelAction] = deque()

    def queue_final(self, text: str) -> None:
        self.actions.append(ModelAction(kind="final", text=text))

    def queue_call(self, name: str, arguments: dict, *, tool_call_id: str) -> None:
        self.actions.append(
            ModelAction(
                kind="call",
                call=CapabilityCall(name=name, arguments=arguments),
                tool_call_id=tool_call_id,
            )
        )

    async def next_turn(self, *_args, **_kwargs) -> ModelAction:
        return self.actions.popleft()


_ADMIN = {"Authorization": "Bearer test-admin"}


def wait_for_run(client: TestClient, run_id: str, *statuses: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        run = client.get(f"/api/v2/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.01)
    raise AssertionError(f"run did not reach {statuses}: {run}")


def test_v2_session_run_debug_and_replay(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", "test-admin")
    with TestClient(create_app()) as client:
        model = FakeRuntimeModel()
        model.queue_final("v2 answer")
        client.app.state.platform.runtime_v2._model = model
        session = client.post("/api/v2/sessions", json={"title": "v2"}).json()
        response = client.post(
            f"/api/v2/sessions/{session['session_id']}/runs",
            json={"message": "hello"},
        )
        assert response.status_code == 202
        run = wait_for_run(client, response.json()["run_id"], "completed")

        stream = client.get(f"/api/v2/runs/{run['run_id']}/stream")
        event_ids = [
            line.removeprefix("id: ")
            for line in stream.text.splitlines()
            if line.startswith("id: ")
        ]
        resumed = client.get(
            f"/api/v2/runs/{run['run_id']}/stream",
            headers={"Last-Event-ID": event_ids[0]},
        )

        messages = client.get(
            f"/api/v2/sessions/{session['session_id']}/messages"
        ).json()
        debug = client.get(f"/api/v2/runs/{run['run_id']}/debug").json()
        replay = client.get(
            f"/api/v2/sessions/{session['session_id']}/replay"
        ).json()

    assert [item["event_type"] for item in messages] == [
        "USER_MESSAGE",
        "ASSISTANT_MESSAGE",
    ]
    assert debug["context_manifests"][0]["prefix_hash"] == session["prefix_hash"]
    assert replay["valid"] is True
    assert "event: ASSISTANT_MESSAGE" in stream.text
    assert event_ids[0] not in resumed.text
    assert "event: RUN_STATUS_CHANGED" in resumed.text


def test_v2_high_risk_write_is_resumed_from_background_approval(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", "test-admin")
    calls = 0

    async def execute(_call, _idempotency_key):
        nonlocal calls
        calls += 1
        return CapabilityResult(status="succeeded", content={"ok": True})

    with TestClient(create_app()) as client:
        platform = client.app.state.platform
        platform.capabilities_v2.register(
            CapabilitySpec(
                name="publish_v2",
                kind=CapabilityKind.TOOL,
                description="publish v2 result",
                input_schema={"type": "object", "properties": {}},
                writes=True,
                risk=RiskLevel.HIGH,
                version="1",
                executor=execute,
            )
        )
        platform.resolver_v2.sync_index()
        model = FakeRuntimeModel()
        model.queue_call("tool_search", {"query": "publish v2"}, tool_call_id="search")
        model.queue_call("publish_v2", {}, tool_call_id="write")
        model.queue_final("done")
        platform.runtime_v2._model = model
        session = client.post("/api/v2/sessions", json={}).json()
        created = client.post(
            f"/api/v2/sessions/{session['session_id']}/runs",
            json={"message": "publish v2"},
        ).json()
        waiting = wait_for_run(client, created["run_id"], "waiting_approval")
        approval_id = waiting["pending_approval_id"]
        response = client.post(
            f"/api/v2/runs/{created['run_id']}/approvals/{approval_id}",
            json={"approved": True, "expected_revision": waiting["revision"]},
        )
        assert response.status_code == 202
        completed = wait_for_run(client, created["run_id"], "completed")

    assert completed["final_text"] == "done"
    assert calls == 1


def test_v2_knowledge_mutation_requires_host_admin_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", "test-admin")
    with TestClient(create_app()) as client:
        denied = client.post(
            "/api/v2/knowledge", json={"title": "guide", "content": "safe process"}
        )
        created = client.post(
            "/api/v2/knowledge",
            json={"title": "guide", "content": "safe process"},
            headers=_ADMIN,
        )
        documents = client.get("/api/v2/knowledge").json()

    assert denied.status_code == 403
    assert created.status_code == 201
    assert documents[0]["document_id"] == created.json()["document_id"]
