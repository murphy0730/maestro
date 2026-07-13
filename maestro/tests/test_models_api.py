"""/models 与 /admin/reload-model 的鉴权与脱敏 (DEF-5)。"""

from fastapi.testclient import TestClient

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.main import app


def _client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    app.state.platform = build_platform(settings=s)
    return TestClient(app), s


def _cfg(api_key: str = "sk-secret-123", pid: str = "p1") -> dict:
    return {
        "llm": {
            "providers": [{"id": pid, "name": "测试", "base_url": "http://x/v1",
                           "api_key": api_key, "model": "m1"}],
            "active_id": pid,
        },
        "embedding": {"providers": [], "active_id": None},
    }


def test_put_models_requires_privileged_token(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    assert c.put("/models", json=_cfg()).status_code == 401
    assert c.put("/models", json=_cfg(),
                 headers={"Authorization": "Bearer wrong"}).status_code == 401
    # 未授权写入不得落盘
    assert c.get("/models").json()["llm"]["providers"] == []


def test_reload_model_requires_privileged_token(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    assert c.post("/admin/reload-model").status_code == 401


def test_get_models_never_returns_plaintext_key(tmp_path, monkeypatch):
    c, s = _client(tmp_path, monkeypatch)
    auth = {"Authorization": f"Bearer {s.privileged_api_token}"}
    assert c.put("/models", json=_cfg(), headers=auth).status_code == 200
    body = c.get("/models").json()
    provider = body["llm"]["providers"][0]
    assert provider["api_key"] == ""
    assert provider["api_key_set"] is True
    assert "sk-secret-123" not in c.get("/models").text


def test_put_with_empty_key_preserves_stored_secret(tmp_path, monkeypatch):
    c, s = _client(tmp_path, monkeypatch)
    auth = {"Authorization": f"Bearer {s.privileged_api_token}"}
    c.put("/models", json=_cfg(), headers=auth)
    # 前端回读到的是脱敏配置 (api_key="")，原样 PUT 回来不得清掉已存密钥
    redacted = c.get("/models").json()
    assert c.put("/models", json=redacted, headers=auth).status_code == 200

    from maestro.foundation import model_config as mc
    stored = mc.load_model_providers()
    assert stored["llm"]["providers"][0]["api_key"] == "sk-secret-123"
    # 显式提供新 key 时则覆盖
    updated = _cfg(api_key="sk-new-456")
    c.put("/models", json=updated, headers=auth)
    stored = mc.load_model_providers()
    assert stored["llm"]["providers"][0]["api_key"] == "sk-new-456"
