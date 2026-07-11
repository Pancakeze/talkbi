import pytest

from app.utils.sql_guard import SQLGuardPolicy, validate_sql


def test_validate_sql_accepts_select():
    validate_sql("SELECT 1")


def test_validate_sql_accepts_with_cte():
    validate_sql("WITH t AS (SELECT 1) SELECT * FROM t LIMIT 10")


def test_validate_sql_rejects_non_select():
    with pytest.raises(ValueError):
        validate_sql("UPDATE users SET id=1")


def test_validate_sql_rejects_dangerous_keywords():
    with pytest.raises(ValueError):
        validate_sql("SELECT 1; DROP TABLE users;")


def test_validate_sql_rejects_comments():
    with pytest.raises(ValueError):
        validate_sql("SELECT 1 -- evil")
    with pytest.raises(ValueError):
        validate_sql("SELECT /* hack */ 1")


def test_validate_sql_requires_limit_when_table_present():
    with pytest.raises(ValueError):
        validate_sql('SELECT a FROM "staging"."ds_1_t"')


def test_validate_sql_rejects_too_large_limit():
    with pytest.raises(ValueError):
        validate_sql(
            'SELECT a FROM "staging"."ds_1_t" LIMIT 100000',
            policy=SQLGuardPolicy(max_limit=1000),
        )


def test_validate_sql_enforces_table_allowlist():
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    validate_sql('SELECT a FROM "staging"."ds_1_t" LIMIT 10', policy=policy)
    with pytest.raises(ValueError):
        validate_sql('SELECT a FROM "staging"."ds_2_t" LIMIT 10', policy=policy)
    with pytest.raises(ValueError):
        validate_sql('SELECT a FROM "staging"."ds_1_t", "public"."users" LIMIT 10', policy=policy)


def test_validate_sql_enforces_schema_when_no_allowlist():
    policy = SQLGuardPolicy(allowed_schemas=("staging",))
    validate_sql('SELECT a FROM "staging"."ds_1_t" LIMIT 10', policy=policy)
    with pytest.raises(ValueError):
        validate_sql('SELECT a FROM "public"."users" LIMIT 10', policy=policy)


def test_validate_sql_rejects_forbidden_function():
    with pytest.raises(ValueError):
        validate_sql("SELECT pg_sleep(10) FROM t LIMIT 1")
    with pytest.raises(ValueError):
        validate_sql("SELECT readfile('/etc/passwd') FROM t LIMIT 1")


def test_validate_sql_rejects_select_into():
    with pytest.raises(ValueError):
        validate_sql('SELECT * INTO copied_data FROM "staging"."ds_1_t" LIMIT 10')
