import io

import pandas as pd

from app.db.session import SessionLocal
from app.models import Conversation, User
from app.services import chat_service
from app.services.chat_service import run_chat_query


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    df = pd.DataFrame(
        {
            "district_name": ["A区", "B区"],
            "congestion_index": [1.2, 3.4],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Traffic", index=False)
    return buf.getvalue()


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


def test_llm_sql_rejected_by_guard_falls_back_to_baseline(client, monkeypatch):
    """CTE table names fail the staging allowlist; chat must still answer via baseline."""
    monkeypatch.setattr(chat_service.settings, "llm_mock_mode", False)

    def _fake_ollama(**kwargs):
        return (
            'WITH t AS (SELECT district_name FROM "staging"."x" LIMIT 100) '
            "SELECT * FROM t LIMIT 100"
        )

    monkeypatch.setattr(chat_service, "ollama_generate", _fake_ollama)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = {
        "file": (
            "chat-fallback.xlsx",
            _xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    up = client.post("/api/data-sources/excel/upload", files=files, headers=headers)
    assert up.status_code == 200, up.text
    ds_id = up.json()["id"]
    physical = up.json()["connection_info"]["staging"]["tables"][0]["table"]

    theme = client.post(
        "/api/theme-libraries",
        json={"name": "chat-llm-guard-fallback", "description": "", "data_source_id": ds_id},
        headers=headers,
    )
    assert theme.status_code == 200, theme.text
    theme_id = theme.json()["id"]
    for col in ("district_name", "congestion_index"):
        fr = client.post(
            f"/api/theme-libraries/{theme_id}/fields",
            json={
                "table_name": physical,
                "field_name": col,
                "alias_zh": col,
                "visible": True,
            },
            headers=headers,
        )
        assert fr.status_code == 200, fr.text

    response = client.post(
        "/api/chat/query",
        json={"prompt": "查看各区指标", "theme_ids": [theme_id]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert len(body["rows"]) >= 1
    assert "WITH" not in body["sql"].upper()
    assert "（Ollama 生成 SQL）" not in body["explanation"]
