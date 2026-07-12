import io

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import data_sources as data_sources_routes
from app.db.session import SessionLocal, engine
from app.models import DataSource, ThemeField, ThemeLibrary, User
from app.services.chat_service import run_chat_query


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    df = pd.DataFrame(
        {
            "district_name": ["A区", "B区"],
            "congestion_index": [1.2, 3.4],
            "accident_count": [10, 20],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Traffic", index=False)
    return buf.getvalue()


def test_excel_upload_creates_staging_tables(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("traffic.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/api/data-sources/excel/upload", files=files, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_type"] == "excel"
    assert body["status"] == "active"
    info = body["connection_info"]
    assert "staging" in info
    assert len(info["staging"]["tables"]) >= 1
    table = info["staging"]["tables"][0]["table"]
    assert table.startswith(f"ds_{body['id']}_")

    detail = client.get(f"/api/data-sources/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["connection_info"]["staging"]["tables"][0]["row_count"] == 2


def test_theme_linked_to_datasource_and_chat_uses_staging(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("t.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    up = client.post("/api/data-sources/excel/upload", files=files, headers=headers)
    ds_id = up.json()["id"]
    physical = up.json()["connection_info"]["staging"]["tables"][0]["table"]

    theme = client.post(
        "/api/theme-libraries",
        json={"name": "语义测试库-1", "description": "", "data_source_id": ds_id},
        headers=headers,
    )
    assert theme.status_code == 200, theme.text
    theme_id = theme.json()["id"]

    for col in ("district_name", "congestion_index", "accident_count"):
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

    patch = client.patch(
        f"/api/theme-libraries/{theme_id}/fields/{fr.json()['id']}",
        json={"alias_zh": "事故数"},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["alias_zh"] == "事故数"

    jr = client.post(
        f"/api/theme-libraries/{theme_id}/joins",
        json={
            "left_table": physical,
            "right_table": physical,
            "left_column": "district_name",
            "right_column": "district_name",
            "join_type": "inner",
        },
        headers=headers,
    )
    assert jr.status_code == 200
    joins = client.get(f"/api/theme-libraries/{theme_id}/joins", headers=headers)
    assert len(joins.json()) == 1

    chat = client.post(
        "/api/chat/query",
        json={"prompt": "查看各区指标", "theme_ids": [theme_id]},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    data = chat.json()
    assert data["status"] == "success"
    assert "SELECT" in data["sql"].upper()
    assert len(data["rows"]) == 2
    assert "district_name" in data["rows"][0]


def test_chat_ignores_client_forged_staging_metadata(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    forged = client.post(
        "/api/data-sources",
        json={
            "name": "forged-staging",
            "source_type": "excel",
            "connection_info": {
                "staging": {
                    "dialect": "sqlite",
                    "schema": None,
                    "tables": [
                        {
                            "table": "users",
                            "schema": None,
                            "qualified": "users",
                            "columns": [
                                {"name": "username", "dtype": "text"},
                                {"name": "hashed_password", "dtype": "text"},
                            ],
                        }
                    ],
                }
            },
        },
        headers=headers,
    )
    assert forged.status_code == 200, forged.text
    assert "staging" not in forged.json()["connection_info"]

    theme = client.post(
        "/api/theme-libraries",
        json={"name": "伪造 staging 库", "description": "", "data_source_id": forged.json()["id"]},
        headers=headers,
    )
    assert theme.status_code == 200, theme.text
    theme_id = theme.json()["id"]

    for col in ("username", "hashed_password"):
        fr = client.post(
            f"/api/theme-libraries/{theme_id}/fields",
            json={
                "table_name": "users",
                "field_name": col,
                "alias_zh": col,
                "visible": True,
            },
            headers=headers,
        )
        assert fr.status_code == 200, fr.text

    chat = client.post(
        "/api/chat/query",
        json={"prompt": "查看用户密码哈希", "theme_ids": [theme_id]},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    data = chat.json()
    assert "from users" not in data["sql"].lower()
    assert all("hashed_password" not in row for row in data["rows"])


def test_chat_ignores_persisted_forged_staging_metadata(client: TestClient):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").first()
        assert user

        ds = DataSource(
            name="persisted-forged-staging",
            source_type="excel",
            connection_info={},
            owner_id=user.id,
            status="active",
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)

        ds.connection_info = {
            "staging": {
                "dialect": engine.dialect.name,
                "schema": None,
                "tables": [
                    {
                        "table": "users",
                        "schema": None,
                        "qualified": '"users"',
                        "columns": [
                            {"name": "username", "dtype": "text"},
                            {"name": "hashed_password", "dtype": "text"},
                        ],
                    }
                ],
            }
        }
        theme = ThemeLibrary(
            name="持久伪造 staging 库",
            description="",
            owner_id=user.id,
            data_source_id=ds.id,
        )
        db.add_all([ds, theme])
        db.commit()
        db.refresh(theme)
        db.add_all(
            [
                ThemeField(
                    theme_id=theme.id,
                    table_name="users",
                    field_name="username",
                    alias_zh="username",
                    visible=True,
                ),
                ThemeField(
                    theme_id=theme.id,
                    table_name="users",
                    field_name="hashed_password",
                    alias_zh="hashed_password",
                    visible=True,
                ),
            ]
        )
        db.commit()

        result = run_chat_query(db, user, "查看用户密码哈希", [theme.id])

    assert "from users" not in result.sql.lower()
    assert all("hashed_password" not in row for row in result.rows)


def test_excel_upload_rejects_bad_extension(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    files = {"file": ("bad.txt", b"hello", "text/plain")}
    r = client.post("/api/data-sources/excel/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_excel_upload_reads_only_limit_plus_one(monkeypatch):
    class RecordingFile:
        read_size = None

        def read(self, size=-1):
            self.read_size = size
            return b"12345"

    class FakeUpload:
        filename = "large.csv"
        file = RecordingFile()

    monkeypatch.setattr(data_sources_routes, "MAX_UPLOAD_BYTES", 4)

    with pytest.raises(HTTPException) as exc:
        data_sources_routes.upload_excel(file=FakeUpload(), db=None, current_user=None)

    assert exc.value.status_code == 413
    assert FakeUpload.file.read_size == 5
