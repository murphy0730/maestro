import json
from pathlib import Path

from maestro.config import Settings, project_root


def test_data_dir_defaults_to_home_maestro(monkeypatch):
    monkeypatch.delenv("MAESTRO_DATA_DIR", raising=False)
    s = Settings()
    assert s.sessions_dir == Path.home() / ".maestro" / "sessions"
    assert s.chroma_dir == Path.home() / ".maestro" / "chroma"


def test_data_dir_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.sessions_dir == tmp_path / "sessions"
    assert s.chroma_dir == tmp_path / "chroma"
    assert s.skills_dir == tmp_path / "skills"
    assert s.knowledge_upload_dir == tmp_path / "knowledge_uploads"
    assert s.audit_log_file == tmp_path / "logs" / "audit.jsonl"


def test_seed_dirs_not_relocated_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    s = Settings()
    # 种子数据随包发布，不走 userData
    assert s.mock_data_dir == project_root() / "data" / "mock"
    assert s.knowledge_dir == project_root() / "data" / "mock" / "knowledge"


def test_settings_json_supplies_llm_config(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    (tmp_path / "settings.json").write_text(
        json.dumps({"llm_api_key": "sk-from-json", "llm_model": "model-json"}),
        encoding="utf-8",
    )
    s = Settings()
    assert s.llm_api_key == "sk-from-json"
    assert s.llm_model == "model-json"


def test_env_overrides_settings_json(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        json.dumps({"llm_api_key": "sk-from-json"}), encoding="utf-8"
    )
    monkeypatch.setenv("LLM_API_KEY", "sk-from-env")
    s = Settings()
    assert s.llm_api_key == "sk-from-env"


def test_settings_json_supplies_mcp_servers(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        json.dumps({"mcp_servers": [{"name": "mes", "command": "python", "args": ["server.py"]}]}),
        encoding="utf-8",
    )
    server = Settings().mcp_servers[0]
    assert server.name == "mes"
    assert server.transport_type == "stdio"
    assert server.args == ["server.py"]


def test_platform_falls_back_to_memory_when_chroma_cannot_open(monkeypatch, tmp_path):
    from maestro.bootstrap import build_platform
    from maestro.foundation.chroma_store import ChromaVectorStore

    def unavailable(self, embedder, persist_dir):
        raise RuntimeError("read-only database")

    monkeypatch.setattr(ChromaVectorStore, "__init__", unavailable)
    platform = build_platform(Settings(vector_backend="chroma", chroma_dir=tmp_path / "chroma"))
    assert type(platform.ingestor._store).__name__ == "VectorStore"
