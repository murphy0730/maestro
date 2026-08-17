"""`/models` 是宿主管理接口，规则与 MCP / Skill 包管理一致。

读开放但永远脱敏；任何改动推理来源的写操作都要特权令牌，缺失时答 403 而非 401。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from maestro.api.app import create_app
from maestro.foundation import model_config as mc

TOKEN = "test-admin-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRIVILEGED_API_TOKEN", TOKEN)
    with TestClient(create_app()) as test_client:
        yield test_client


def _auth() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


def _config(api_key: str = "sk-secret", active: bool = True) -> dict:
    return {
        "llm": {
            "providers": [
                {
                    "id": "p1",
                    "name": "DeepSeek",
                    "base_url": "https://api.deepseek.com",
                    "api_key": api_key,
                    "model": "deepseek-chat",
                }
            ],
            "active_id": "p1" if active else None,
        },
        "embedding": {"providers": [], "active_id": None},
    }


def test_empty_config_returns_the_empty_shape(client: TestClient) -> None:
    body = client.get("/models").json()
    assert body == {
        "llm": {"providers": [], "active_id": None},
        "embedding": {"providers": [], "active_id": None},
    }


def test_saving_requires_the_privileged_token(client: TestClient) -> None:
    assert client.put("/models", json=_config()).status_code == 403
    assert (
        client.put("/models", json=_config(), headers={"Authorization": "Bearer wrong"}).status_code
        == 403
    )
    assert client.post("/models/test", json={"section": "llm"}).status_code == 403


def test_saved_key_is_never_echoed_back(client: TestClient) -> None:
    client.put("/models", json=_config(), headers=_auth())

    provider = client.get("/models").json()["llm"]["providers"][0]
    assert provider["api_key"] == ""
    assert provider["api_key_set"] is True
    # 明文只应存在于磁盘。
    assert mc.load_model_providers()["llm"]["providers"][0]["api_key"] == "sk-secret"


def test_resaving_with_a_blank_key_keeps_the_stored_one(client: TestClient) -> None:
    client.put("/models", json=_config(), headers=_auth())
    # 前端回读到的是脱敏结果，原样保存不应把密钥清空。
    client.put("/models", json=_config(api_key=""), headers=_auth())

    assert mc.load_model_providers()["llm"]["providers"][0]["api_key"] == "sk-secret"
    assert client.get("/models").json()["llm"]["providers"][0]["api_key_set"] is True


def test_activating_a_provider_reconfigures_the_running_client(client: TestClient) -> None:
    platform = client.app.state.platform
    before = platform.llm

    client.put("/models", json=_config(), headers=_auth())

    assert platform.llm.model == "deepseek-chat"
    # 协调器按引用持有这个客户端，热更新必须原地发生。
    assert platform.llm is before


def test_clearing_the_active_provider_falls_back_to_the_flat_settings(client: TestClient) -> None:
    platform = client.app.state.platform
    client.put("/models", json=_config(), headers=_auth())

    client.put("/models", json=_config(active=False), headers=_auth())

    assert platform.llm.model == platform.settings.llm_model


def test_writing_models_leaves_other_settings_sections_alone(client: TestClient) -> None:
    path = mc.settings_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcp_servers": {"echo": {"command": "x"}}}), encoding="utf-8")

    client.put("/models", json=_config(), headers=_auth())

    assert json.loads(path.read_text(encoding="utf-8"))["mcp_servers"] == {"echo": {"command": "x"}}


def test_testing_a_provider_reports_missing_fields_without_failing(client: TestClient) -> None:
    body = client.post("/models/test", json={"section": "llm"}, headers=_auth()).json()
    assert body["ok"] is False
    assert "model" in body["error"]

    body = client.post(
        "/models/test", json={"section": "llm", "model": "deepseek-chat"}, headers=_auth()
    ).json()
    assert body["ok"] is False
    assert "api_key" in body["error"]


def test_testing_an_unknown_section_is_rejected(client: TestClient) -> None:
    response = client.post("/models/test", json={"section": "nope"}, headers=_auth())
    assert response.status_code == 422
