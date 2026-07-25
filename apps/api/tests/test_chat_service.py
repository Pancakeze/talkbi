from app.db.session import SessionLocal
from app.models import Conversation, User
from app.services.chat_service import run_chat_query


def test_run_chat_query_bar(client):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").first()
        assert user
        r = run_chat_query(db, user, "各区平均拥堵", [])
    assert r.status == "success"
    assert "SELECT" in r.sql.upper()
    assert r.chart_spec["chartType"] == "bar"
    assert len(r.rows) >= 1


def test_run_chat_query_scatter(client):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").first()
        assert user
        r = run_chat_query(db, user, "拥堵与事故相关性散点", [])
    assert r.chart_spec["chartType"] == "scatter"
    assert "accident_count" in r.sql


def test_selected_unqueryable_theme_does_not_return_mock_data(client):
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    theme = client.post(
        "/api/theme-libraries",
        json={
            "name": "chat-unqueryable-theme",
            "description": "",
            "data_source_id": None,
        },
        headers=headers,
    )
    assert theme.status_code == 200, theme.text

    with SessionLocal() as db:
        conversations_before = db.query(Conversation).count()

    response = client.post(
        "/api/chat/query",
        json={"prompt": "分析真实业务数据", "theme_ids": [theme.json()["id"]]},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unable to query the selected themes."
    with SessionLocal() as db:
        assert db.query(Conversation).count() == conversations_before
