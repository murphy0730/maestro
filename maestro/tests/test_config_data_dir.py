from maestro.config import Settings, project_root


def test_data_dir_defaults_to_project_data(monkeypatch):
    monkeypatch.delenv("MAESTRO_DATA_DIR", raising=False)
    s = Settings()
    assert s.sessions_dir == project_root() / "data" / "sessions"
    assert s.chroma_dir == project_root() / "data" / "chroma"


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
