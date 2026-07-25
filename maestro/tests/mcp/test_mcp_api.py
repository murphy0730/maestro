"""`/mcp/servers` is host administration, so it follows the Skill API's rules.

Reading is open; anything that installs, changes or removes capabilities needs
the privileged token and answers 403 — never 401 — without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maestro.api.app import create_app

SERVER = Path(__file__).parent / "servers" / "echo_server.py"
TOKEN = "test-admin-token"


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", TOKEN)
    with TestClient(create_app()) as test_client:
        yield test_client


def _payload(name: str = "echo") -> dict:
    return {
        "name": name,
        "command": sys.executable,
        "args": [str(SERVER)],
        "env": {},
        "enabled": True,
    }


def test_listing_starts_empty(client: TestClient) -> None:
    assert client.get("/mcp/servers").json() == {"servers": []}


def test_mutations_require_the_privileged_token(client: TestClient) -> None:
    for response in (
        client.put("/mcp/servers/echo", json=_payload()),
        client.delete("/mcp/servers/echo"),
        client.post("/mcp/servers/echo/reconnect"),
    ):
        assert response.status_code == 403


def test_upsert_connects_and_publishes_capabilities(client: TestClient) -> None:
    response = client.put(
        "/mcp/servers/echo", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert {tool["capability"] for tool in body["tools"]} == {
        "mcp__echo__echo",
        "mcp__echo__leak_env",
    }
    capabilities = client.app.state.platform.capabilities
    assert capabilities.require("mcp__echo__echo") is not None

    listed = client.get("/mcp/servers").json()["servers"]
    assert [item["name"] for item in listed] == ["echo"]


def test_env_values_are_not_echoed_back(client: TestClient) -> None:
    payload = _payload() | {"env": {"API_TOKEN": "s3cret"}}

    body = client.put(
        "/mcp/servers/echo", json=payload, headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    assert body["env_keys"] == ["API_TOKEN"]
    assert "s3cret" not in str(body)


def test_delete_removes_config_and_capabilities(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    client.put("/mcp/servers/echo", json=_payload(), headers=headers)

    assert client.delete("/mcp/servers/echo", headers=headers).status_code == 200

    assert client.get("/mcp/servers").json() == {"servers": []}
    with pytest.raises(KeyError):
        client.app.state.platform.capabilities.require("mcp__echo__echo")


def test_deleting_an_unknown_server_is_404(client: TestClient) -> None:
    response = client.delete(
        "/mcp/servers/nope", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 404


def test_a_broken_server_is_reported_not_raised(client: TestClient) -> None:
    payload = _payload("broken") | {"command": "/nonexistent/binary", "args": []}

    body = client.put(
        "/mcp/servers/broken", json=payload, headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    assert body["status"] == "error"
    assert body["error"]
    assert body["tools"] == []


def test_name_mismatch_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/mcp/servers/other", json=_payload("echo"), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 400
