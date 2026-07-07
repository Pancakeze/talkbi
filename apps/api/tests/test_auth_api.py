import pytest

from app.core.config import DEFAULT_SECRET_KEY, Settings
from app.db.init_db import _should_seed_demo_users


def test_login_success(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_invalid_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid username/password"


def test_me_requires_auth(client):
    r = client.get("/api/me")
    assert r.status_code == 401


def test_me_with_token(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_production_like_environment_rejects_default_secret_key():
    for environment in ("staging", "production"):
        config = Settings(environment=environment, secret_key=DEFAULT_SECRET_KEY)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            config.validate_security()


def test_demo_seed_users_are_development_and_test_only():
    assert _should_seed_demo_users("development")
    assert _should_seed_demo_users("test")
    assert not _should_seed_demo_users("staging")
    assert not _should_seed_demo_users("production")
