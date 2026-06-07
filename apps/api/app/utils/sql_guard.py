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
    "sqlite_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "readfile",
    "load_extension",
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(r"\b(from|join)\b\s+([^\s,;]+)", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)


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


def _extract_tables(sql_text: str) -> set[str]:
    tables: set[str] = set()
    for _, raw in _FROM_JOIN_RE.findall(sql_text):
        ident = _normalize_ident(raw)
        # Ignore subqueries: FROM (SELECT ...)
        if ident.startswith("("):
            continue
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


def _has_forbidden_function(sql_text: str) -> bool:
    return any(re.search(rf"\b{re.escape(fn)}\s*\(", sql_text, re.IGNORECASE) for fn in _FORBIDDEN_FUNCTIONS)


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
    if _has_forbidden_function(cleaned):
        raise ValueError("Unsafe SQL detected.")

    tables = _extract_tables(cleaned)
    lim = _extract_limit(cleaned)
    if tables:
        if lim is None:
            raise ValueError("LIMIT clause is required.")
        if lim > policy.max_limit:
            raise ValueError("LIMIT is too large.")
    if policy.allowed_tables is not None:
        if not tables:
            raise ValueError("SQL must reference an allowed table.")
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



