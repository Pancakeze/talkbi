def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_meta_exposes_non_sensitive_runtime_flags(client):
    resp = client.get("/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert "llm_mock_mode" in body
    assert "ollama_base_url" in body
    assert "ollama_model" in body
    assert "database_dialect" in body


def test_production_rejects_default_secret(monkeypatch):
    from app.core.config import DEFAULT_SECRET_KEY, settings
    from app.main import _validate_runtime_settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)

    try:
        _validate_runtime_settings()
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("production must reject the default SECRET_KEY")
