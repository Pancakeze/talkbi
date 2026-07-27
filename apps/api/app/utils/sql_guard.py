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
    "pg_file_write",
    "pg_file_unlink",
    "pg_file_rename",
    "lo_import",
    "lo_export",
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
    "readfile",
    "writefile",
    "load_extension",
    "sqlite_sleep",
)
_FORBIDDEN_FUNCTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(fn) for fn in _FORBIDDEN_FUNCTIONS) + r")\s*\(",
    re.IGNORECASE,
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_FROM_RE = re.compile(r"\bfrom\b", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bjoin\b\s+([^\s,;]+)", re.IGNORECASE)
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
    # Keep dots but strip quoting chars.
    t = token.strip()
    # remove trailing punctuation like "," or ")"
    t = t.rstrip(",")
    # Strip common quoting.
    t = t.replace('"', "").replace("`", "")
    return t


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
    if not ref or ref.startswith("("):
        return None

    parts = ref.split()
    if not parts:
        return None
    if parts[0].lower() == "only" and len(parts) > 1:
        token = parts[1]
    elif parts[0].lower() == "lateral":
        if len(parts) < 2 or parts[1].startswith("("):
            return None
        token = parts[1]
    else:
        token = parts[0]

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
    return tables


def _extract_limit(sql_text: str) -> Optional[int]:
    m = _LIMIT_RE.search(sql_text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


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

    words = {w.lower() for w in _WORD_RE.findall(cleaned)}
    if any(k in words for k in _FORBIDDEN_KEYWORDS):
        raise ValueError("Unsafe SQL detected.")
    if _FORBIDDEN_FUNCTION_RE.search(cleaned):
        raise ValueError("Unsafe SQL detected.")

    tables = _extract_tables(cleaned)
    lim = _extract_limit(cleaned)
    if policy.allowed_tables is not None and not tables:
        raise ValueError("Query must reference an allowed table.")
    if tables:
        if lim is None:
            raise ValueError("LIMIT clause is required.")
        if lim > policy.max_limit:
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



