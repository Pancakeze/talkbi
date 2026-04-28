from fastapi.testclient import TestClient


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_chart_crud_and_dashboard_layout_happy_path(client: TestClient):
    token = _login(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/api/charts",
        json={
            "title": "E2E Saved Chart",
            "chart_type": "bar",
            "chart_spec": {"chartType": "bar", "title": "E2E Saved Chart", "x": "district_name", "y": "accident_count"},
        },
        headers=headers,
    )
    assert create.status_code == 200, create.text
    chart_id = create.json()["id"]

    charts = client.get("/api/charts", headers=headers)
    assert charts.status_code == 200
    assert any(c["id"] == chart_id for c in charts.json())

    d = client.post("/api/dashboards", json={"name": "我的仪表盘"}, headers=headers)
    assert d.status_code == 200, d.text
    dash_id = d.json()["id"]

    empty = client.get(f"/api/dashboards/{dash_id}/layout", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    up = client.patch(
        f"/api/dashboards/{dash_id}/layout",
        json={
            "items": [
                {
                    "chart_id": chart_id,
                    "title": "卡片标题",
                    "position_x": 0,
                    "position_y": 0,
                    "width": 6,
                    "height": 4,
                }
            ]
        },
        headers=headers,
    )
    assert up.status_code == 200, up.text
    assert up.json()["ok"] is True
    assert up.json()["count"] == 1

    after = client.get(f"/api/dashboards/{dash_id}/layout", headers=headers)
    assert after.status_code == 200
    items = after.json()["items"]
    assert len(items) == 1
    assert items[0]["chart_id"] == chart_id
    assert items[0]["title"] == "卡片标题"


def test_dashboard_layout_rejects_unowned_chart(client: TestClient):
    admin_token = _login(client, "admin", "admin123")
    analyst_token = _login(client, "analyst", "analyst123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    c = client.post(
        "/api/charts",
        json={"title": "Analyst Chart", "chart_type": "line", "chart_spec": {"chartType": "line", "title": "Analyst Chart"}},
        headers=analyst_headers,
    )
    assert c.status_code == 200, c.text
    analyst_chart_id = c.json()["id"]

    d = client.post("/api/dashboards", json={"name": "Admin Dash"}, headers=admin_headers)
    assert d.status_code == 200, d.text
    dash_id = d.json()["id"]

    bad = client.patch(
        f"/api/dashboards/{dash_id}/layout",
        json={
            "items": [
                {
                    "chart_id": analyst_chart_id,
                    "title": "should fail",
                    "position_x": 0,
                    "position_y": 0,
                    "width": 6,
                    "height": 4,
                }
            ]
        },
        headers=admin_headers,
    )
    assert bad.status_code == 400
    assert "not owned" in bad.json()["detail"]

