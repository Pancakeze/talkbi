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


def test_validate_sql_rejects_postgres_xml_allowlist_bypass():
    """table_to_xml / query_to_xml dump other relations without FROM/JOIN refs."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT table_to_xml(\'users\'::regclass, true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT database_to_xml(true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        (
            'SELECT query_to_xml(concat(\'SELECT hashed_password FRO\',\'M users\'), '
            'true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1'
        ),
        'SELECT cursor_to_xml(\'c\'::refcursor, 10, true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT schema_to_xml(\'public\', true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_file_and_dblink_side_effects():
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT lo_export(1, \'/tmp/x\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_file_write(\'/tmp/x\', \'x\', false) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT dblink(\'dbname=postgres\', \'select 1\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT writefile(\'/tmp/x\', \'x\') FROM "staging"."ds_1_t" LIMIT 1',
        (
            'SELECT dblink_fetch(dblink_open(\'c\', \'dbname=talkbi\', '
            '\'SELECT hashed_password FRO\'||\'M users\'), 100) '
            'FROM "staging"."ds_1_t" LIMIT 100'
        ),
        'SELECT dblink_send_query(\'c\', \'SELECT 1\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT dblink_get_result(\'c\') FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_quoted_forbidden_functions():
    """Identifier quotes must not evade the dangerous-function denylist."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT "table_to_xml"(\'users\'::regclass, true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT "pg_read_file"(\'/etc/passwd\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_catalog."table_to_xml"(\'users\'::regclass, true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT "pg_catalog"."query_to_xml"(concat(\'SELECT 1\'), true, true, \'\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT "lo_export"(1, \'/tmp/x\') FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_table_shorthand_allowlist_bypass():
    """PostgreSQL TABLE rel can read arbitrary relations without a FROM token."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT * FROM "staging"."ds_1_t", (TABLE users) u LIMIT 10',
        'SELECT u.* FROM "staging"."ds_1_t" CROSS JOIN (TABLE users) AS u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" JOIN (TABLE users) u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", (TABLE ONLY "users") u LIMIT 10',
    ):
        with pytest.raises(ValueError, match="Table is not allowed"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_lateral_join_allowlist_bypass():
    """JOIN LATERAL <table> must still enforce the table allowlist."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN LATERAL users LIMIT 10',
        'SELECT u.hashed_password FROM "staging"."ds_1_t" t JOIN LATERAL users u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" LEFT JOIN LATERAL ONLY users ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN LATERAL "public"."users" LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN LATERAL public.users LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", LATERAL users LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", LATERAL ONLY users LIMIT 10',
    ):
        with pytest.raises(ValueError, match="Table is not allowed"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_only_paren_relation_allowlist_bypass():
    """PostgreSQL/SQL-standard ONLY (rel) must still enforce the table allowlist."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT u.hashed_password FROM "staging"."ds_1_t" t CROSS JOIN ONLY (users) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", ONLY (users) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", ONLY ( users ) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" LEFT JOIN ONLY (public.users) u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" RIGHT JOIN ONLY ("users") u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" FULL JOIN ONLY (pg_catalog.pg_authid) u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" NATURAL JOIN ONLY (users) LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", ONLY(users) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN ONLY (pg_shadow) u LIMIT 10',
        # JOIN regex used to truncate at whitespace inside ONLY (...), skipping allowlist.
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN ONLY (  users  ) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN ONLY ( "public"."users" ) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" JOIN ONLY ( "pg_catalog"."pg_authid" ) u ON true LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t", ONLY (  "public"  .  "users"  ) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN ONLY ( "public" . "users" ) u LIMIT 10',
        'SELECT * FROM "staging"."ds_1_t" CROSS JOIN ONLY( "users" ) u LIMIT 10',
    ):
        with pytest.raises(ValueError, match="Table is not allowed"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_unicode_escaped_forbidden_functions():
    """U& unicode identifier escapes must not hide denylisted function names."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT U&"table\\005fto\\005fxml"(\'users\'::regclass, true, true, \'\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"pg\\005fread\\005ffile"(\'/etc/passwd\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_catalog.U&"query\\005fto\\005fxml"(concat(\'SELECT 1\'), true, true, \'\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_additional_lo_dblink_and_admin_functions():
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT lo_get(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT loread(lo_open(1, 262144), 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT lo_from_bytea(0, \'x\'::bytea) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT dblink_connect_u(\'c\', \'dbname=postgres\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_execute_server_program(\'id\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_ls_logicalsnapdir() FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_read_file\x00(\'/etc/passwd\') FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_ts_stat_nested_sql_allowlist_bypass():
    """ts_stat executes a text SQL query via SPI; FROM can be hidden in the string."""
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        (
            "SELECT ts_stat('SELECT username::tsvector FRO'||'M users') "
            'FROM "staging"."ds_1_t" LIMIT 1'
        ),
        (
            "SELECT pg_catalog.ts_stat('SELECT rolname::tsvector FRO'||'M pg_authid') "
            'FROM "staging"."ds_1_t" LIMIT 1'
        ),
        (
            "SELECT \"ts_stat\"('SELECT to_tsvector(''simple'', passwd) FRO'||'M pg_shadow') "
            'FROM "staging"."ds_1_t" LIMIT 100'
        ),
        (
            "SELECT U&\"ts\\005fstat\"('SELECT username::tsvector FRO'||'M users') "
            'FROM "staging"."ds_1_t" LIMIT 1'
        ),
        (
            "SELECT ts_stat(chr(83)||chr(69)||chr(76)||chr(69)||chr(67)||chr(84)"
            "||' username::tsvector '||chr(70)||chr(82)||chr(79)||chr(77)||' users') "
            'FROM "staging"."ds_1_t" LIMIT 100'
        ),
        (
            'SELECT s.* FROM "staging"."ds_1_t" CROSS JOIN LATERAL '
            "(SELECT ts_stat('SELECT username::tsvector FRO'||'M users')) s LIMIT 100"
        ),
        (
            "SELECT ts_rewrite('a'::tsquery, "
            "'SELECT ''a''::tsquery, ''b''::tsquery FRO'||'M users') "
            'FROM "staging"."ds_1_t" LIMIT 1'
        ),
        'SELECT pg_terminate_backend(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_cancel_backend(pg_backend_pid()) FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)
