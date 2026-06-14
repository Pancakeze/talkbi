from app.db.session import SessionLocal
from app.models import DataSource, ThemeField, ThemeLibrary, User
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


def test_chat_rejects_forged_staging_metadata(client):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").first()
        assert user

        ds = DataSource(
            name="forged",
            source_type="excel",
            status="active",
            owner_id=user.id,
            connection_info={
                "staging": {
                    "dialect": "sqlite",
                    "tables": [
                        {
                            "table": "users",
                            "qualified": '"users"',
                            "columns": [{"name": "hashed_password", "dtype": "object"}],
                        }
                    ],
                }
            },
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)

        theme = ThemeLibrary(
            name=f"forged-users-{ds.id}",
            description="forged metadata",
            owner_id=user.id,
            data_source_id=ds.id,
            status="published",
        )
        db.add(theme)
        db.commit()
        db.refresh(theme)

        db.add(
            ThemeField(
                theme_id=theme.id,
                table_name="users",
                field_name="hashed_password",
                alias_zh="password hash",
                visible=True,
            )
        )
        db.commit()

        r = run_chat_query(db, user, "预览用户密码", [theme.id])

    assert "hashed_password" not in r.sql
    assert all("hashed_password" not in row for row in r.rows)
