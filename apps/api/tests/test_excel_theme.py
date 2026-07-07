import io

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


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


def test_chat_ignores_forged_staging_metadata_for_system_table(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    forged_source = client.post(
        "/api/data-sources",
        json={
            "name": "forged-staging-source",
            "source_type": "excel",
            "connection_info": {
                "staging": {
                    "dialect": "sqlite",
                    "tables": [
                        {
                            "table": "users",
                            "schema": None,
                            "qualified": '"users"',
                            "columns": [
                                {"name": "username", "dtype": "object"},
                                {"name": "hashed_password", "dtype": "object"},
                            ],
                        }
                    ],
                }
            },
        },
        headers=headers,
    )
    assert forged_source.status_code == 200, forged_source.text
    ds_id = forged_source.json()["id"]

    theme = client.post(
        "/api/theme-libraries",
        json={"name": "伪造 staging 元数据测试", "description": "", "data_source_id": ds_id},
        headers=headers,
    )
    assert theme.status_code == 200, theme.text
    theme_id = theme.json()["id"]

    for col in ("username", "hashed_password"):
        field = client.post(
            f"/api/theme-libraries/{theme_id}/fields",
            json={
                "table_name": "users",
                "field_name": col,
                "alias_zh": col,
                "visible": True,
            },
            headers=headers,
        )
        assert field.status_code == 200, field.text

    chat = client.post(
        "/api/chat/query",
        json={"prompt": "查看用户密码哈希", "theme_ids": [theme_id]},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    data = chat.json()
    assert "users" not in data["sql"].lower()
    assert "hashed_password" not in data["sql"].lower()
    assert all("hashed_password" not in row for row in data["rows"])


def test_excel_upload_rejects_bad_extension(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    files = {"file": ("bad.txt", b"hello", "text/plain")}
    r = client.post("/api/data-sources/excel/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_upload_reader_rejects_oversized_file_without_full_buffer(monkeypatch):
    from app.api.routes import data_sources

    class TrackingFile:
        def __init__(self, payload: bytes):
            self._buffer = io.BytesIO(payload)
            self.bytes_read = 0

        def read(self, size: int = -1) -> bytes:
            chunk = self._buffer.read(size)
            self.bytes_read += len(chunk)
            return chunk

    class Upload:
        def __init__(self, payload: bytes):
            self.file = TrackingFile(payload)

    monkeypatch.setattr(data_sources, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(data_sources, "_UPLOAD_READ_CHUNK_BYTES", 4)
    upload = Upload(b"x" * 25)

    with pytest.raises(HTTPException) as exc_info:
        data_sources._read_upload_limited(upload)  # noqa: SLF001

    assert exc_info.value.status_code == 413
    assert upload.file.bytes_read == 11
