import pytest


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


def test_production_like_runtime_rejects_default_secret(monkeypatch):
    from app.core.config import DEFAULT_SECRET_KEY, settings
    from app.main import _assert_safe_runtime_config

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)

    with pytest.raises(RuntimeError):
        _assert_safe_runtime_config()

    monkeypatch.setattr(settings, "secret_key", "not-the-default-secret")
    _assert_safe_runtime_config()


def test_demo_seed_only_runs_in_development_or_test(monkeypatch):
    from app.core.config import settings
    from app.main import _should_seed_demo_data

    monkeypatch.setattr(settings, "environment", "development")
    assert _should_seed_demo_data()

    monkeypatch.setattr(settings, "environment", "test")
    assert _should_seed_demo_data()

    monkeypatch.setattr(settings, "environment", "production")
    assert not _should_seed_demo_data()
