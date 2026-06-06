from fastapi.testclient import TestClient


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_protected_endpoints_require_auth(client: TestClient):
    cases = [
        ("get", "/api/me"),
        ("get", "/api/data-sources"),
        ("post", "/api/data-sources/excel/upload"),
        ("get", "/api/theme-libraries"),
        ("post", "/api/chat/query"),
        ("get", "/api/charts"),
        ("post", "/api/charts"),
        ("get", "/api/dashboards"),
        ("post", "/api/dashboards"),
    ]
    for method, path in cases:
        resp = client.request(method, path, json={} if method == "post" else None)
        assert resp.status_code == 401, f"{method.upper()} {path} should be 401, got {resp.status_code}"


def test_theme_is_not_visible_to_other_user(client: TestClient):
    admin_token = _login(client, "admin", "admin123")
    analyst_token = _login(client, "analyst", "analyst123")

    create = client.post(
        "/api/theme-libraries",
        json={"name": "私有库-AUTHZ"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create.status_code == 200, create.text
    theme_id = create.json()["id"]

    listed = client.get(
        "/api/theme-libraries", headers={"Authorization": f"Bearer {analyst_token}"}
    )
    assert listed.status_code == 200
    assert all(t["id"] != theme_id for t in listed.json())

    detail = client.get(
        f"/api/theme-libraries/{theme_id}",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert detail.status_code == 404

    add_field = client.post(
        f"/api/theme-libraries/{theme_id}/fields",
        json={
            "table_name": "any",
            "field_name": "x",
            "alias_zh": "x",
            "visible": True,
        },
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert add_field.status_code == 404


def test_theme_create_with_unowned_data_source_is_rejected(client: TestClient):
    admin_token = _login(client, "admin", "admin123")
    analyst_token = _login(client, "analyst", "analyst123")

    ds = client.post(
        "/api/data-sources",
        json={"name": "private-ds", "source_type": "mysql", "connection_info": {}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ds.status_code == 200, ds.text
    ds_id = ds.json()["id"]

    bad = client.post(
        "/api/theme-libraries",
        json={"name": "AUTHZ-DS-LEAK", "data_source_id": ds_id},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert bad.status_code == 400
    assert "data_source_id" in bad.json()["detail"]


def test_chat_does_not_trust_forged_staging_metadata(client: TestClient):
    analyst_token = _login(client, "analyst", "analyst123")
    headers = {"Authorization": f"Bearer {analyst_token}"}

    ds = client.post(
        "/api/data-sources",
        json={
            "name": "forged-users-ds",
            "source_type": "excel",
            "connection_info": {
                "staging": {
                    "tables": [
                        {
                            "sheet_name": "Users",
                            "table": "users",
                            "schema": None,
                            "qualified": "users",
                            "row_count": 2,
                            "columns": [
                                {"name": "username", "dtype": "object"},
                                {"name": "hashed_password", "dtype": "object"},
                            ],
                        }
                    ]
                }
            },
        },
        headers=headers,
    )
    assert ds.status_code == 200, ds.text

    theme = client.post(
        "/api/theme-libraries",
        json={"name": "AUTHZ-FORGED-STAGING", "data_source_id": ds.json()["id"]},
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
        json={"prompt": "查看用户", "theme_ids": [theme_id]},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert "users" not in body["sql"].lower()
    assert "hashed_password" not in body["sql"]
    assert all("hashed_password" not in row for row in body["rows"])
