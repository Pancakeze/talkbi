from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_FORBIDDEN_KEYWORDS = (
    # DDL/DML
    "drop",
    "delete",
    "truncate",
    "alter",
    "update",
    "insert",
    "into",
    "create",
    "replace",
    "grant",
    "revoke",
    # execution / side effects
    "copy",
    "attach",
    "detach",
    "vacuum",
    "analyze",
    # Custom U& escape selector. Default U&"\\xxxx" decoding is enough for
    # legitimate identifiers; UESCAPE enables denylist-hiding variants the
    # scanner might not fully normalize (e.g. UESCAPE E'\\\\').
    "uescape",
)

_FORBIDDEN_FUNCTIONS = (
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_ls_logdir",
    "pg_ls_waldir",
    "pg_ls_archive_statusdir",
    "pg_ls_tmpdir",
    "pg_ls_logicalsnapdir",
    "pg_ls_logicalmapdir",
    "pg_ls_replslotdir",
    "pg_file_write",
    "pg_file_unlink",
    "pg_file_rename",
    "pg_file_sync",
    "pg_execute_server_program",
    "lo_import",
    "lo_export",
    "lo_get",
    "lo_put",
    "lo_from_bytea",
    "lo_create",
    "lo_unlink",
    "lo_open",
    "loread",
    "lowrite",
    # PostgreSQL XML helpers can dump arbitrary relations / run nested SQL
    # without putting the victim table in FROM/JOIN, bypassing allowlists.
    "table_to_xml",
    "table_to_xmlschema",
    "table_to_xml_and_xmlschema",
    "query_to_xml",
    "query_to_xmlschema",
    "query_to_xml_and_xmlschema",
    "cursor_to_xml",
    "cursor_to_xmlschema",
    "database_to_xml",
    "database_to_xmlschema",
    "database_to_xml_and_xmlschema",
    "schema_to_xml",
    "schema_to_xmlschema",
    "schema_to_xml_and_xmlschema",
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "dblink_connect_u",
    "dblink_open",
    "dblink_fetch",
    "dblink_close",
    "dblink_send_query",
    "dblink_get_result",
    "dblink_get_connections",
    "dblink_disconnect",
    "dblink_cancel_query",
    # Text-search helpers that execute a caller-supplied SQL string via SPI,
    # allowing allowlist bypass when FROM is obfuscated inside the string.
    "ts_stat",
    "ts_rewrite",
    # Session disruption / DoS primitives that must not run in chat SQL.
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_sleep_for",
    "set_config",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_promote",
    "pg_switch_wal",
    "pg_wal_replay_pause",
    "pg_create_restore_point",
    "pg_advisory_lock",
    "pg_advisory_lock_shared",
    "pg_advisory_unlock",
    "pg_advisory_unlock_shared",
    "pg_advisory_xact_lock",
    "pg_advisory_xact_lock_shared",
    "pg_advisory_unlock_all",
    "pg_try_advisory_lock",
    "pg_try_advisory_lock_shared",
    "pg_try_advisory_xact_lock",
    "pg_try_advisory_xact_lock_shared",
    # tablefunc helpers: crosstab runs caller SQL text; connectby takes a table name.
    "crosstab",
    "crosstab2",
    "crosstab3",
    "crosstab4",
    "connectby",
    "readfile",
    "writefile",
    "load_extension",
    "sqlite_sleep",
)
_FORBIDDEN_FUNCTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(fn) for fn in _FORBIDDEN_FUNCTIONS) + r")\s*\(",
    re.IGNORECASE,
)
# PostgreSQL U&"..." unicode identifier/string escapes: \xxxx or \+xxxxxx
_UNICODE_ESCAPE_RE = re.compile(
    r"\\(?:\+([0-9A-Fa-f]{6})|([0-9A-Fa-f]{4}))",
)
# Custom-escape form: U&"table!005fto!005fxml" UESCAPE '!'
# Without decoding, denylisted names never appear as literal text.
_UAND_IDENT_RE = re.compile(
    r"U&\"([^\"]*)\"(?:\s*UESCAPE\s+'(.)')?",
    re.IGNORECASE,
)

_LIMIT_KEYWORD_RE = re.compile(r"\blimit\b", re.IGNORECASE)
# PostgreSQL SQL-standard row bound: FETCH { FIRST | NEXT } [ count ] { ROW | ROWS } ...
# Equivalent to LIMIT and must be enforced the same way (including nested LIMITs).
_FETCH_KEYWORD_RE = re.compile(r"\bfetch\s+(?:first|next)\b", re.IGNORECASE)
_FETCH_ROW_TAIL_RE = re.compile(r"^rows?\s+(?:only|with\s+ties)\b", re.IGNORECASE)
# After a literal LIMIT n, only clause boundaries / subquery closers are valid.
# Reject expressions such as LIMIT 1+999999 or LIMIT 200*200 that bypass max_limit.
# Do NOT allow a bare comma here: SQLite/MySQL `LIMIT offset, count` would otherwise
# parse only the offset (e.g. LIMIT 0, 50000 → lim=0) while returning `count` rows.
# Subquery forms like (SELECT ... LIMIT 1), outer_col still work via the `)` alternative.
_AFTER_LIMIT_OK_RE = re.compile(r"^(?:offset|fetch|for)\b|^\)", re.IGNORECASE)
_FROM_RE = re.compile(r"\bfrom\b", re.IGNORECASE)
# Include optional LATERAL / ONLY so JOIN LATERAL users is not truncated to "LATERAL".
_JOIN_RE = re.compile(
    r"\bjoin\b\s+((?:lateral\s+)?(?:only\s+)?[^\s,;]+)",
    re.IGNORECASE,
)
# PostgreSQL TABLE shorthand: (TABLE users) / TABLE ONLY public.users
# can reference relations without a normal FROM/JOIN identifier token.
_TABLE_SHORTHAND_RE = re.compile(
    r"\btable\b\s+(?:only\s+)?([^\s,;)]+)",
    re.IGNORECASE,
)
# One relation identifier, optionally schema-qualified, with optional quoting /
# whitespace around the dot (PostgreSQL accepts ONLY ( "public" . "users" )).
_RELATION_IDENT = (
    r"(?:\"[^\"]+\"|`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)"
    r"(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*))?"
)
# SQL-standard / PostgreSQL: ONLY ( relation_name ) at start of a table_ref token
_ONLY_PAREN_RELATION_RE = re.compile(
    rf"^\(\s*({_RELATION_IDENT})\s*\)",
    re.IGNORECASE,
)
# Same form scanned anywhere so JOIN regex truncation (ONLY \s*\() cannot skip it.
_ONLY_PAREN_RELATION_ANYWHERE_RE = re.compile(
    rf"\bonly\s*\(\s*({_RELATION_IDENT})\s*\)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)
_CLAUSE_BOUNDARIES = (
    "where",
    "group",
    "order",
    "having",
    "limit",
    "offset",
    "union",
    "intersect",
    "except",
    "fetch",
    "window",
)


def _strip_sql(sql_text: str) -> str:
    return sql_text.strip().rstrip(";").strip()


def _normalize_ident(token: str) -> str:
    # Keep dots but strip quoting chars / insignificant identifier whitespace.
    t = token.strip()
    # remove trailing punctuation like "," or ")"
    t = t.rstrip(",")
    # Strip common quoting.
    t = t.replace('"', "").replace("`", "")
    # "public" . "users" / public  .  users → public.users
    t = re.sub(r"\s*\.\s*", ".", t)
    t = re.sub(r"\s+", "", t)
    return t


def _decode_postgres_unicode_escapes(sql_text: str, *, escape_char: str = "\\") -> str:
    """Decode PostgreSQL U& unicode escapes so denylist matching sees real names."""
    if not escape_char or len(escape_char) != 1:
        return sql_text
    pattern = re.compile(
        re.escape(escape_char) + r"(?:\+([0-9A-Fa-f]{6})|([0-9A-Fa-f]{4}))",
    )

    def _repl(match: re.Match[str]) -> str:
        hex_digits = match.group(1) or match.group(2)
        try:
            return chr(int(hex_digits, 16))
        except ValueError:
            return match.group(0)

    return pattern.sub(_repl, sql_text)


def _expand_postgres_uand_identifiers(sql_text: str) -> str:
    """
    Expand U&"..." [UESCAPE 'x'] identifiers to their decoded names.

    Default U& escapes use backslash; attackers can also choose a custom escape
    via UESCAPE, e.g. U&"table!005fto!005fxml" UESCAPE '!' → table_to_xml.
    """

    def _repl(match: re.Match[str]) -> str:
        body = match.group(1)
        escape_char = match.group(2) or "\\"
        return _decode_postgres_unicode_escapes(body, escape_char=escape_char)

    return _UAND_IDENT_RE.sub(_repl, sql_text)


def _sql_for_function_scan(sql_text: str) -> str:
    """
    Strip identifier quoting so denylisted calls still match when written as
    "table_to_xml"(...) or pg_catalog."pg_read_file"(...).

    Also decode U&"table\\005fto\\005fxml" and custom UESCAPE forms that would
    otherwise hide denylisted names from a literal regex match.
    """
    expanded = _expand_postgres_uand_identifiers(sql_text)
    return _decode_postgres_unicode_escapes(expanded.replace('"', "").replace("`", ""))


def _keyword_at(sql_text: str, idx: int, keyword: str) -> bool:
    end = idx + len(keyword)
    if sql_text[idx:end].lower() != keyword:
        return False
    before = sql_text[idx - 1] if idx > 0 else " "
    after = sql_text[end] if end < len(sql_text) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _find_from_clause_end(sql_text: str, start: int) -> int:
    depth = 0
    quote: str | None = None
    idx = start
    while idx < len(sql_text):
        ch = sql_text[idx]
        if quote:
            if ch == quote:
                quote = None
            idx += 1
            continue
        if ch in ('"', "'", "`"):
            quote = ch
            idx += 1
            continue
        if ch == "(":
            depth += 1
            idx += 1
            continue
        if ch == ")":
            if depth == 0:
                return idx
            depth -= 1
            idx += 1
            continue
        if depth == 0 and any(_keyword_at(sql_text, idx, kw) for kw in _CLAUSE_BOUNDARIES):
            return idx
        idx += 1
    return len(sql_text)


def _split_top_level_commas(sql_text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    for idx, ch in enumerate(sql_text):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'", "`"):
            quote = ch
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            continue
        if ch == "," and depth == 0:
            parts.append(sql_text[start:idx])
            start = idx + 1
    parts.append(sql_text[start:])
    return parts


def _first_table_ident(table_ref: str) -> str | None:
    ref = table_ref.strip()
    if not ref:
        return None

    # Parenthesized TABLE shorthand: (TABLE users) alias
    if ref.startswith("("):
        inner = ref[1:].lstrip()
        shorthand = _TABLE_SHORTHAND_RE.match(inner)
        if shorthand:
            ident = _normalize_ident(shorthand.group(1))
            if ident:
                return ident
        # Subquery / row constructor — inner FROM/JOIN scan covers SELECT forms.
        if re.match(r"(?:select|with|values)\b", inner, re.IGNORECASE):
            return None
        # SQLite accepts parenthesized relation refs such as (users) / ("users")
        # / (main.users). Skipping these previously let LLM SQL join the users
        # table while only the staging allowlist entry was extracted.
        paren_rel = _ONLY_PAREN_RELATION_RE.match(ref)
        if paren_rel:
            ident = _normalize_ident(paren_rel.group(1))
            return ident or None
        only_inside = re.match(
            rf"^\(\s*only\s+({_RELATION_IDENT})\s*\)",
            ref,
            re.IGNORECASE,
        )
        if only_inside:
            ident = _normalize_ident(only_inside.group(1))
            return ident or None
        return None

    parts = ref.split()
    if not parts:
        return None

    idx = 0
    # JOIN/FROM items may be written as: LATERAL ONLY schema.table
    if parts[idx].lower() == "lateral":
        idx += 1
        if idx >= len(parts):
            return None
        # LATERAL (subquery|relation) — reuse parenthesized parsing.
        if parts[idx].startswith("("):
            return _first_table_ident(" ".join(parts[idx:]))
    if parts[idx].lower() == "only":
        idx += 1
        if idx >= len(parts):
            return None
        # SQL standard form: ONLY ( relation_name ) — parentheses are optional
        # in PostgreSQL but still valid and must be allowlisted.
        only_paren = _ONLY_PAREN_RELATION_RE.match(" ".join(parts[idx:]))
        if only_paren:
            ident = _normalize_ident(only_paren.group(1))
            return ident or None

    if parts[idx].lower() == "table":
        shorthand = _TABLE_SHORTHAND_RE.match(" ".join(parts[idx:]))
        if not shorthand:
            return None
        token = shorthand.group(1)
    else:
        token = parts[idx]

    # ONLY(users) without whitespace after ONLY
    if token.lower().startswith("only("):
        only_paren = _ONLY_PAREN_RELATION_RE.match(token[4:])
        if only_paren:
            ident = _normalize_ident(only_paren.group(1))
            return ident or None

    ident = _normalize_ident(token)
    if not ident or ident.startswith("("):
        return None
    return ident


def _extract_tables(sql_text: str) -> set[str]:
    tables: set[str] = set()
    for match in _FROM_RE.finditer(sql_text):
        clause_end = _find_from_clause_end(sql_text, match.end())
        from_clause = sql_text[match.end() : clause_end]
        for table_ref in _split_top_level_commas(from_clause):
            ident = _first_table_ident(table_ref)
            if ident:
                tables.add(ident)
    for raw in _JOIN_RE.findall(sql_text):
        ident = _first_table_ident(raw)
        if ident:
            tables.add(ident)
    # Catch TABLE shorthand even when JOIN regex only tokenizes "(TABLE".
    for raw in _TABLE_SHORTHAND_RE.findall(sql_text):
        ident = _normalize_ident(raw)
        if ident:
            tables.add(ident)
    # Catch ONLY (rel) even when JOIN regex truncates to "ONLY (".
    for raw in _ONLY_PAREN_RELATION_ANYWHERE_RE.findall(sql_text):
        ident = _normalize_ident(raw)
        if ident:
            tables.add(ident)
    return tables


def _paren_depth_at_positions(sql_text: str) -> list[int]:
    """
    Return the parenthesis nesting depth at each character index.

    Depth ignores quoted spans so identifiers/literals containing '(' do not
    skew top-level LIMIT/FETCH detection.
    """
    depths = [0] * len(sql_text)
    depth = 0
    quote: str | None = None
    for idx, ch in enumerate(sql_text):
        depths[idx] = depth
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'", "`"):
            quote = ch
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
    return depths


def _parse_limit_at(sql_text: str, match_end: int) -> int:
    rest = sql_text[match_end:].lstrip()
    literal = re.match(r"(\d+)", rest)
    if not literal:
        raise ValueError("LIMIT must be a literal integer.")
    after = rest[literal.end() :].lstrip()
    if after and not _AFTER_LIMIT_OK_RE.match(after):
        raise ValueError("LIMIT must be a literal integer.")
    return int(literal.group(1))


def _parse_fetch_at(sql_text: str, match_end: int) -> int:
    rest = sql_text[match_end:].lstrip()
    literal = re.match(r"(\d+)\s+", rest)
    if literal:
        after = rest[literal.end() :].lstrip()
        if not _FETCH_ROW_TAIL_RE.match(after):
            raise ValueError("FETCH row count must be a literal integer.")
        return int(literal.group(1))
    if _FETCH_ROW_TAIL_RE.match(rest):
        # FETCH FIRST ROW ONLY / FETCH NEXT ROWS ONLY → count defaults to 1
        return 1
    raise ValueError("FETCH row count must be a literal integer.")


def _extract_limits(sql_text: str, *, top_level_only: bool = False) -> list[int]:
    """
    Return LIMIT values. Only bare integer literals are accepted so
    expressions like LIMIT 1+N cannot bypass max_limit while still executing.

    When top_level_only is set, nested subquery LIMITs are ignored so they
    cannot satisfy the required outer row bound.
    """
    depths = _paren_depth_at_positions(sql_text) if top_level_only else None
    values: list[int] = []
    for match in _LIMIT_KEYWORD_RE.finditer(sql_text):
        if depths is not None and depths[match.start()] != 0:
            continue
        values.append(_parse_limit_at(sql_text, match.end()))
    return values


def _extract_fetches(sql_text: str, *, top_level_only: bool = False) -> list[int]:
    """
    Return FETCH FIRST/NEXT row counts (PostgreSQL's LIMIT equivalent).

    Bare omitted counts default to 1. Expressions such as FETCH FIRST (100*100)
    must be rejected so they cannot bypass max_limit while still executing.

    When top_level_only is set, nested FETCH clauses are ignored so they cannot
    satisfy the required outer row bound.
    """
    depths = _paren_depth_at_positions(sql_text) if top_level_only else None
    values: list[int] = []
    for match in _FETCH_KEYWORD_RE.finditer(sql_text):
        if depths is not None and depths[match.start()] != 0:
            continue
        values.append(_parse_fetch_at(sql_text, match.end()))
    return values


def _extract_row_bounds(sql_text: str, *, top_level_only: bool = False) -> list[int]:
    """LIMIT and FETCH FIRST/NEXT bounds that cap returned rows."""
    return _extract_limits(sql_text, top_level_only=top_level_only) + _extract_fetches(
        sql_text, top_level_only=top_level_only
    )


@dataclass(frozen=True)
class SQLGuardPolicy:
    max_limit: int = 1000
    allowed_schemas: tuple[str, ...] = ("staging",)
    allowed_tables: Optional[frozenset[str]] = None  # normalized identifiers


def validate_sql(
    sql_text: str,
    *,
    policy: Optional[SQLGuardPolicy] = None,
) -> None:
    """
    Best-effort SQL guard for generated SQL.
    - Only allows SELECT / WITH ... SELECT
    - Blocks DDL/DML and multi-statement/comment tricks
    - Optionally enforces allowed staging schemas/tables and LIMIT upper bound
    """
    policy = policy or SQLGuardPolicy()

    cleaned = _strip_sql(sql_text)
    low = cleaned.lower()

    if not (low.startswith("select") or low.startswith("with ")):
        raise ValueError("Only SELECT statements are allowed.")

    # Block multi-statement and comment-based evasion.
    if ";" in cleaned:
        raise ValueError("Multiple statements are not allowed.")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise ValueError("SQL comments are not allowed.")
    if "\x00" in cleaned:
        raise ValueError("Unsafe SQL detected.")

    words = {w.lower() for w in _WORD_RE.findall(cleaned)}
    if any(k in words for k in _FORBIDDEN_KEYWORDS):
        raise ValueError("Unsafe SQL detected.")
    if _FORBIDDEN_FUNCTION_RE.search(_sql_for_function_scan(cleaned)):
        raise ValueError("Unsafe SQL detected.")

    tables = _extract_tables(cleaned)
    # Validate every LIMIT/FETCH literal (including nested) against max_limit so
    # expressions/huge nested bounds cannot slip through, but require a
    # top-level bound so nested LIMIT 1 cannot leave the outer result unbounded.
    all_row_bounds = _extract_row_bounds(cleaned, top_level_only=False)
    top_level_row_bounds = _extract_row_bounds(cleaned, top_level_only=True)
    if policy.allowed_tables is not None and not tables:
        raise ValueError("Query must reference an allowed table.")
    if tables:
        if not top_level_row_bounds:
            raise ValueError("LIMIT clause is required.")
        if any(lim > policy.max_limit for lim in all_row_bounds):
            raise ValueError("LIMIT is too large.")
    if policy.allowed_tables is not None:
        norm_allowed = policy.allowed_tables
        for t in tables:
            if t not in norm_allowed:
                raise ValueError("Table is not allowed.")
    else:
        # Schema check when table allowlist isn't provided:
        # allow bare table name (no schema) for sqlite, but if schema is present enforce it.
        for t in tables:
            if "." in t:
                schema = t.split(".", 1)[0]
                if schema not in policy.allowed_schemas:
                    raise ValueError("Schema is not allowed.")



