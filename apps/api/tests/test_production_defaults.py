import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db import init_db
from app.db.base import Base
from app.models import User


def test_production_rejects_default_secret_key():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(environment="production").validate_production_safety()


def test_staging_rejects_default_secret_key():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(environment="staging").validate_production_safety()


def test_production_rejects_empty_or_short_secret_key():
    # Empty/weak keys still mint valid HS256 JWTs — reject them in protected envs.
    for secret in ("", "   ", "x", "short-but-not-default-key"):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            Settings(environment="production", secret_key=secret).validate_production_safety()
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            Settings(environment="staging", secret_key=secret).validate_production_safety()


def test_production_accepts_custom_secret_key():
    Settings(
        environment="production",
        secret_key="replace-with-a-long-random-secret",
    ).validate_production_safety()


def test_demo_seed_is_disabled_in_production(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    monkeypatch.setattr(
        init_db,
        "settings",
        Settings(environment="production", secret_key="replace-with-a-long-random-secret"),
    )

    with Session() as db:
        init_db.seed_data(db)
        assert db.query(User).count() == 0
