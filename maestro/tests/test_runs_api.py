from fastapi.testclient import TestClient
from datetime import UTC, datetime

from maestro.api.app import create_app
from maestro.foundation.llm import LLMError
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.events import RunEvent
from maestro.runtime.model import ModelAction


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", "test-admin")
    return TestClient(create_app())


_ADMIN = {"Authorization": "Bearer test-admin"}


def test_create_run_returns_identity(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/runs", json={"session_id": "s1", "message": "解释 OEE", "skill_names": []})
    assert response.status_code == 202
    assert response.json()["path"] in {"fast", "structured"}
    assert response.json()["run_id"]
    assert response.json()["status"] in {"running_fast", "running_structured"}


def test_first_question_uses_the_model_to_title_a_new_session(tmp_path, monkeypatch) -> None:
    generated = "分析本周A产线延期订单原因与对策建议"

    with _client(tmp_path, monkeypatch) as client:
        session = client.post("/sessions", json={"title": "新任务"}).json()

        async def complete(system, messages, **_kwargs):
            assert "不超过15个字符" in system
            assert messages == [{"role": "user", "content": "为什么本周 A 产线订单延期？"}]
            return f"《{generated}》"

        client.app.state.platform.llm.complete = complete
        response = client.post(
            "/runs",
            json={"session_id": session["session_id"], "message": "为什么本周 A 产线订单延期？"},
        )
        saved = next(
            item for item in client.get("/sessions").json()
            if item["session_id"] == session["session_id"]
        )

    assert response.status_code == 202
    assert saved["title"] == generated[:15]
    assert len(saved["title"]) <= 15


def test_session_title_falls_back_to_the_first_question_when_the_model_fails(
    tmp_path, monkeypatch
) -> None:
    question = "请分析未来三个月所有产线的整体产能风险"

    with _client(tmp_path, monkeypatch) as client:
        session = client.post("/sessions", json={"title": "新任务"}).json()

        async def fail(*_args, **_kwargs):
            raise LLMError("offline")

        client.app.state.platform.llm.complete = fail
        response = client.post(
            "/runs", json={"session_id": session["session_id"], "message": question}
        )
        saved = next(
            item for item in client.get("/sessions").json()
            if item["session_id"] == session["session_id"]
        )

    assert response.status_code == 202
    assert saved["title"] == question[:15]


def test_first_question_does_not_replace_a_manually_named_session(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        session = client.post("/sessions", json={"title": "七月交付复盘"}).json()

        async def unexpected(*_args, **_kwargs):
            raise AssertionError("manual titles must not trigger title generation")

        client.app.state.platform.llm.complete = unexpected
        response = client.post(
            "/runs", json={"session_id": session["session_id"], "message": "开始分析"}
        )
        saved = next(
            item for item in client.get("/sessions").json()
            if item["session_id"] == session["session_id"]
        )

    assert response.status_code == 202
    assert saved["title"] == "七月交付复盘"


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
        imported = client.post("/skills/import", files={"file": ("SKILL.md", content, "text/markdown")}, headers=_ADMIN)
        assert imported.status_code == 200
        assert client.get("/skills").json()["skills"][0]["name"] == "local-skill"
        assert client.post("/skills/local-skill/trust", json={"trusted": True}, headers=_ADMIN).status_code == 200


def test_skill_mutation_endpoints_require_administrator(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        content = b"---\nname: guarded\ndescription: guarded\n---\nDo work.\n"
        assert client.post("/skills/import", files={"file": ("SKILL.md", content, "text/markdown")}).status_code == 403
        assert client.post("/skills/import", files={"file": ("SKILL.md", content, "text/markdown")}, headers=_ADMIN).status_code == 200
        assert client.post("/skills/guarded/trust", json={"trusted": True}).status_code == 403
        assert client.delete("/skills/guarded/trust").status_code == 403
        assert client.delete("/skills/guarded").status_code == 403


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


def test_terminal_run_persists_assistant_reply_in_its_session(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/runs", json={"session_id": "history", "message": "hello"})
        assert created.status_code == 202
        client.get(f"/runs/{created.json()['run_id']}/stream")
        messages = client.get("/sessions/history/messages").json()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["run_id"] == created.json()["run_id"]
    assert messages[1]["content"]


def test_approved_run_persists_assistant_reply_in_its_session(tmp_path, monkeypatch) -> None:
    class WriteThenAnswer:
        async def next_turn(self, _context, _capabilities, messages=None):
            if any(message.get("role") == "tool" for message in messages or []):
                return ModelAction(kind="final", text="审批后的任务已完成。")
            return ModelAction(
                kind="call",
                call=CapabilityCall(name="test_write", arguments={}),
            )

    async def execute(_call, _idempotency_key):
        return CapabilityResult(status="succeeded", content={"ok": True})

    with _client(tmp_path, monkeypatch) as client:
        platform = client.app.state.platform
        platform.capabilities.register(
            CapabilitySpec(
                name="test_write",
                kind=CapabilityKind.TOOL,
                risk=RiskLevel.HIGH,
                writes=True,
                executor=execute,
            )
        )
        platform.runtime._model = WriteThenAnswer()
        created = client.post(
            "/runs", json={"session_id": "approved-history", "message": "执行写操作"}
        ).json()
        client.get(f"/runs/{created['run_id']}/stream")
        waiting = client.get(f"/runs/{created['run_id']}").json()
        approval = waiting["pending_approvals"][0]
        completed = client.post(
            f"/runs/{created['run_id']}/approvals/{approval['approval_id']}",
            json={"approved": True, "expected_revision": waiting["revision"]},
        )
        messages = client.get("/sessions/approved-history/messages").json()

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["run_id"] == created["run_id"]
    assert messages[1]["content"] == "审批后的任务已完成。"


def test_failed_run_persists_visible_assistant_message(tmp_path, monkeypatch) -> None:
    class UnknownCapabilityModel:
        async def next_turn(self, _context, _capabilities, messages=None):
            return ModelAction(
                kind="call",
                call=CapabilityCall(name="missing_capability", arguments={}),
            )

    with _client(tmp_path, monkeypatch) as client:
        client.app.state.platform.runtime._model = UnknownCapabilityModel()
        created = client.post(
            "/runs", json={"session_id": "failed-history", "message": "触发失败"}
        ).json()
        client.get(f"/runs/{created['run_id']}/stream")
        messages = client.get("/sessions/failed-history/messages").json()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["run_id"] == created["run_id"]
    assert "运行失败" in messages[1]["content"]


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
