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


def test_validate_sql_rejects_select_into_side_effect():
    with pytest.raises(ValueError):
        validate_sql('SELECT * INTO leaked_copy FROM "staging"."ds_1_t" LIMIT 10')


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
        validate_sql("SELECT 1", policy=policy)


def test_validate_sql_enforces_table_allowlist_for_comma_joins():
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    validate_sql(
        'SELECT a.id, b.id FROM "staging"."ds_1_t" a, "staging"."ds_1_t" b LIMIT 10',
        policy=policy,
    )
    with pytest.raises(ValueError):
        validate_sql(
            'SELECT t.a, u.username FROM "staging"."ds_1_t" t, users u LIMIT 10',
            policy=policy,
        )


def test_validate_sql_enforces_schema_when_no_allowlist():
    policy = SQLGuardPolicy(allowed_schemas=("staging",))
    validate_sql('SELECT a FROM "staging"."ds_1_t" LIMIT 10', policy=policy)
    with pytest.raises(ValueError):
        validate_sql('SELECT a FROM "public"."users" LIMIT 10', policy=policy)


def test_validate_sql_enforces_schema_for_comma_joins():
    policy = SQLGuardPolicy(allowed_schemas=("staging",))
    with pytest.raises(ValueError):
        validate_sql(
            'SELECT t.a, u.username FROM "staging"."ds_1_t" t, "public"."users" u LIMIT 10',
            policy=policy,
        )


def test_validate_sql_rejects_forbidden_function():
    with pytest.raises(ValueError):
        validate_sql("SELECT pg_sleep(10) FROM t LIMIT 1")
    for fn in ("pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file", "readfile", "load_extension"):
        with pytest.raises(ValueError):
            validate_sql(f"SELECT {fn}('/etc/passwd')")
