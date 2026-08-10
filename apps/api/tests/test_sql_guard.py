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


def test_validate_sql_rejects_parenthesized_relation_allowlist_bypass():
    """
    SQLite accepts FROM/JOIN (users) as a real table reference. The guard used to
    skip parenthesized refs that were not TABLE shorthand / SELECT subqueries, so
    LLM SQL like SELECT * FROM ds_1_t, (users) u LIMIT 1 passed the staging
    allowlist while returning users.hashed_password in chat rows.
    """
    policy = SQLGuardPolicy(
        max_limit=200,
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"ds_1_t"}),
    )
    validate_sql(
        'SELECT * FROM ds_1_t, (SELECT id FROM ds_1_t LIMIT 1) x LIMIT 1',
        policy=policy,
    )
    validate_sql(
        'SELECT * FROM ds_1_t, (VALUES (1)) v LIMIT 1',
        policy=policy,
    )
    for sql in (
        'SELECT * FROM ds_1_t, (users) u LIMIT 1',
        'SELECT * FROM "ds_1_t", (users) LIMIT 1',
        'SELECT * FROM ds_1_t JOIN (users) u ON true LIMIT 1',
        'SELECT * FROM ds_1_t CROSS JOIN (users) LIMIT 1',
        'SELECT * FROM ds_1_t LEFT JOIN (users) u ON ds_1_t.id = u.id LIMIT 1',
        'SELECT * FROM ds_1_t, ("users") u LIMIT 1',
        'SELECT * FROM ds_1_t, ( main.users ) u LIMIT 1',
        'SELECT * FROM (users) LIMIT 1',
        'SELECT hashed_password FROM (users) LIMIT 1',
        'SELECT * FROM ds_1_t, LATERAL (users) u LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Table is not allowed|Query must reference"):
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


def test_validate_sql_rejects_custom_uescape_forbidden_functions():
    """
    Custom UESCAPE must not hide denylisted function names.

    PostgreSQL accepts U&"table!005fto!005fxml" UESCAPE '!' as table_to_xml(...),
    which dumps arbitrary relations without putting them in FROM/JOIN.
    """
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT U&"table!005fto!005fxml" UESCAPE \'!\'(\'users\'::regclass, true, true, \'\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"pg!005fread!005ffile" UESCAPE \'!\'(\'/etc/passwd\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"lo!005fexport" UESCAPE \'!\'(1, \'/tmp/x\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"table#005fto#005fxml" UESCAPE \'#\'(\'users\'::regclass, true, true, \'\') '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_catalog.U&"query!005fto!005fxml"UESCAPE\'!\'('
        "concat('SELECT 1'), true, true, '') "
        'FROM "staging"."ds_1_t" LIMIT 1',
        # Default-looking escapes with an explicit UESCAPE backslash must still decode.
        "SELECT U&\"table\\005fto\\005fxml\" UESCAPE E'\\\\'('users'::regclass, true, true, '') "
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


def test_validate_sql_rejects_pg_read_file_old_adminpack_alias():
    """
    PostgreSQL keeps pg_read_file_old as an adminpack 1.0 compatibility alias
    that still executes the pg_read_file implementation. Denylisting only
    pg_read_file left a concrete chat SQL bypass that returns server file
    contents when the DB role can read files (default docker superuser).
    """
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT pg_read_file_old(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_catalog.pg_read_file_old(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT "pg_read_file_old"(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"pg\\005fread\\005ffile\\005fold"(\'/etc/passwd\', 0, 100000) '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_sleep_until(now() + interval \'1 hour\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_rotate_logfile_old() FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_pg_file_read_adminpack_alias():
    """
    adminpack 1.0 registers pg_file_read as an SQL-callable alias whose prosrc
    is still pg_read_file. The guard already blocked pg_read_file / pg_read_file_old
    and pg_file_write, but missed this read-side name — chat SQL could return
    server file contents under a privileged DB role.
    """
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT pg_file_read(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_catalog.pg_file_read(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT "pg_file_read"(\'/etc/passwd\', 0, 100000) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"pg\\005ffile\\005fread"(\'/etc/passwd\', 0, 100000) '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT U&"pg!005ffile!005fread" UESCAPE \'!\'(\'/etc/passwd\', 0, 100000) '
        'FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_file_length(\'/etc/passwd\') FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_logdir_ls() FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_logfile_rotate() FROM "staging"."ds_1_t" LIMIT 1',
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


def test_validate_sql_rejects_limit_expressions_that_bypass_max_limit():
    """DB engines evaluate LIMIT expressions; the guard must not trust the first digits."""
    policy = SQLGuardPolicy(
        max_limit=200,
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    validate_sql('SELECT a FROM "staging"."ds_1_t" LIMIT 200', policy=policy)
    validate_sql(
        'SELECT a FROM (SELECT a FROM "staging"."ds_1_t" LIMIT 10) x LIMIT 20',
        policy=policy,
    )
    for sql in (
        'SELECT a FROM "staging"."ds_1_t" LIMIT 1+999999',
        'SELECT a FROM "staging"."ds_1_t" LIMIT 200*200',
        'SELECT a FROM "staging"."ds_1_t" LIMIT (999)',
        'SELECT a FROM "staging"."ds_1_t" LIMIT 1e9',
        'SELECT * FROM (SELECT a FROM "staging"."ds_1_t" LIMIT 1) x LIMIT 1+999999',
        'SELECT a FROM "staging"."ds_1_t" LIMIT 001 + 500',
    ):
        with pytest.raises(ValueError, match="LIMIT"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_limit_offset_comma_count_bypass():
    """
    SQLite (and MySQL) accept LIMIT offset, count. If the guard treats a trailing
    comma as harmless and only parses the first integer, LIMIT 0, 50000 looks like
    lim=0 while SQLite returns 50000 rows that chat materializes into memory.

    Subquery forms that put `)` between LIMIT and an outer SELECT-list comma must
    still be accepted: (SELECT ... LIMIT 1), col ...
    """
    policy = SQLGuardPolicy(
        max_limit=200,
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    validate_sql(
        'SELECT (SELECT a FROM "staging"."ds_1_t" LIMIT 1), a '
        'FROM "staging"."ds_1_t" LIMIT 10',
        policy=policy,
    )
    validate_sql(
        'SELECT a FROM "staging"."ds_1_t" LIMIT 200 OFFSET 10',
        policy=policy,
    )
    for sql in (
        'SELECT * FROM "staging"."ds_1_t" LIMIT 0, 50000',
        'SELECT * FROM "staging"."ds_1_t" LIMIT 1, 9999',
        'SELECT * FROM "staging"."ds_1_t" LIMIT 10, 201',
        'SELECT * FROM "staging"."ds_1_t" LIMIT 0,200',
        'SELECT * FROM "staging"."ds_1_t" LIMIT 5 , 10',
    ):
        with pytest.raises(ValueError, match="LIMIT"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_fetch_first_that_bypasses_max_limit():
    """
    PostgreSQL FETCH FIRST/NEXT is LIMIT-equivalent. A nested LIMIT 1 must not
    satisfy the guard while an outer FETCH FIRST 50000 still returns huge rowsets
    that chat materializes into memory.
    """
    policy = SQLGuardPolicy(
        max_limit=200,
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    validate_sql(
        'SELECT a FROM "staging"."ds_1_t" FETCH FIRST 200 ROWS ONLY',
        policy=policy,
    )
    validate_sql(
        'SELECT a FROM "staging"."ds_1_t" FETCH NEXT ROW ONLY',
        policy=policy,
    )
    for sql in (
        (
            'SELECT * FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1) '
            "FETCH FIRST 50000 ROWS ONLY"
        ),
        (
            'SELECT * FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1) '
            "OFFSET 0 FETCH NEXT 50000 ROW ONLY"
        ),
        'SELECT a FROM "staging"."ds_1_t" FETCH FIRST 999999 ROWS ONLY',
        'SELECT a FROM "staging"."ds_1_t" ORDER BY 1 FETCH FIRST 50000 ROWS WITH TIES',
        (
            'SELECT * FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1) '
            "FETCH FIRST (100*100) ROWS ONLY"
        ),
    ):
        with pytest.raises(ValueError, match="LIMIT|FETCH"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_nested_limit_that_leaves_outer_unbounded():
    """
    A subquery LIMIT must not satisfy the required row bound: chat materializes
    every returned row, so an outer SELECT without LIMIT/FETCH can OOM on a
    large staging sheet (up to MAX_ROWS_PER_SHEET).
    """
    policy = SQLGuardPolicy(
        max_limit=200,
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    # Nested + outer bound remains valid.
    validate_sql(
        (
            'SELECT a FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1) LIMIT 50'
        ),
        policy=policy,
    )
    validate_sql(
        (
            'SELECT a FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1) '
            "FETCH FIRST 50 ROWS ONLY"
        ),
        policy=policy,
    )
    for sql in (
        (
            'SELECT * FROM "staging"."ds_1_t" WHERE EXISTS '
            '(SELECT 1 FROM "staging"."ds_1_t" LIMIT 1)'
        ),
        (
            'SELECT * FROM "staging"."ds_1_t" WHERE id IN '
            '(SELECT id FROM "staging"."ds_1_t" LIMIT 1)'
        ),
        (
            'SELECT a.* FROM "staging"."ds_1_t" a JOIN '
            '(SELECT * FROM "staging"."ds_1_t" LIMIT 1) b ON true'
        ),
        'SELECT * FROM (SELECT * FROM "staging"."ds_1_t" LIMIT 1) x',
        (
            'WITH x AS (SELECT * FROM "staging"."ds_1_t" LIMIT 1) '
            'SELECT * FROM "staging"."ds_1_t"'
        ),
    ):
        with pytest.raises(ValueError, match="LIMIT"):
            validate_sql(sql, policy=policy)


def test_validate_sql_rejects_admin_dos_and_tablefunc_helpers():
    policy = SQLGuardPolicy(
        allowed_schemas=("staging",),
        allowed_tables=frozenset({"staging.ds_1_t"}),
    )
    for sql in (
        'SELECT pg_sleep_for(\'10 minutes\') FROM "staging"."ds_1_t" LIMIT 1',
        "SELECT set_config('statement_timeout','0',true) FROM \"staging\".\"ds_1_t\" LIMIT 1",
        'SELECT pg_reload_conf() FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_promote() FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_switch_wal() FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_advisory_lock(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_advisory_lock_shared(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_try_advisory_lock(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_try_advisory_lock_shared(1) FROM "staging"."ds_1_t" LIMIT 1',
        'SELECT pg_advisory_xact_lock_shared(1) FROM "staging"."ds_1_t" LIMIT 1',
        (
            "SELECT crosstab(concat('SELECT username::text, ''c''::text, "
            "hashed_password::text FRO','M users')) "
            'FROM "staging"."ds_1_t" LIMIT 1'
        ),
        'SELECT connectby(\'users\',\'id\',\'parent_id\',\'1\',0) FROM "staging"."ds_1_t" LIMIT 1',
    ):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            validate_sql(sql, policy=policy)
