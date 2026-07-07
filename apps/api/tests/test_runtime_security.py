import pytest

from app.core.config import DEFAULT_SECRET_KEY, settings, validate_runtime_settings
from app.db.init_db import seed_data


def test_runtime_settings_reject_default_secret_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)

    with pytest.raises(RuntimeError):
        validate_runtime_settings()


def test_runtime_settings_allow_default_secret_in_development(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)

    validate_runtime_settings()


def test_seed_data_skips_demo_credentials_outside_development(monkeypatch):
    class ExplodingDB:
        def query(self, *args, **kwargs):
            raise AssertionError("seed_data should not query or write in production")

    monkeypatch.setattr(settings, "environment", "production")

    seed_data(ExplodingDB())
