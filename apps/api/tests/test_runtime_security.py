import pytest

from app.core import config
from app import main


def test_rejects_default_secret_in_protected_environment(monkeypatch):
    monkeypatch.setattr(config.settings, "environment", "production")
    monkeypatch.setattr(config.settings, "secret_key", config.DEV_SECRET_KEY)

    with pytest.raises(RuntimeError):
        config.validate_runtime_settings()


def test_allows_default_secret_in_development(monkeypatch):
    monkeypatch.setattr(config.settings, "environment", "development")
    monkeypatch.setattr(config.settings, "secret_key", config.DEV_SECRET_KEY)

    config.validate_runtime_settings()


def test_demo_seed_is_not_enabled_for_production(monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "production")
    assert not main._should_seed_demo_data()

    monkeypatch.setattr(main.settings, "environment", "development")
    assert main._should_seed_demo_data()
