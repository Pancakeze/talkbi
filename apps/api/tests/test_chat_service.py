from app.db.session import SessionLocal
from app.models import User
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
