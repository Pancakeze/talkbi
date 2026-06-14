import pytest

from app.core.config import DEV_SECRET_KEY, settings, validate_runtime_settings


def test_runtime_settings_reject_default_secret_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEV_SECRET_KEY)

    with pytest.raises(RuntimeError):
        validate_runtime_settings()


def test_runtime_settings_allow_default_secret_in_development(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "secret_key", DEV_SECRET_KEY)

    validate_runtime_settings()
