import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DEFAULT_SECRET_KEY, Settings
from app.db import init_db
from app.db.base import Base
from app.models import User
from app.models import entities  # noqa: F401 - register models


def test_settings_reject_default_secret_in_production():
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key=DEFAULT_SECRET_KEY)


def test_settings_accept_custom_secret_in_production():
    settings = Settings(environment="production", secret_key="not-the-default-secret")
    assert settings.secret_key == "not-the-default-secret"


def test_seed_data_skips_demo_users_in_production(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(init_db.settings, "environment", "production")

    with Session() as db:
        init_db.seed_data(db)
        assert db.query(User).count() == 0
