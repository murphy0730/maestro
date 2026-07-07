from scheduling_platform.sidecar_entry import resolve_bind


def test_resolve_bind_defaults(monkeypatch):
    monkeypatch.delenv("MAESTRO_BACKEND_PORT", raising=False)
    assert resolve_bind() == ("127.0.0.1", 8000)


def test_resolve_bind_reads_env(monkeypatch):
    monkeypatch.setenv("MAESTRO_BACKEND_PORT", "9123")
    assert resolve_bind() == ("127.0.0.1", 9123)
