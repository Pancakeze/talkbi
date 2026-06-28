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
    "readfile",
    "load_extension",
    "sqlite_sleep",
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(r"\b(from|join)\b\s+([^\s,;]+)", re.IGNORECASE)
_FROM_CLAUSE_RE = re.compile(
    r"\bfrom\b\s+(.*?)(?=\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\bhaving\b|\blimit\b|\bunion\b|\bintersect\b|\bexcept\b|\boffset\b|$)",
    re.IGNORECASE | re.DOTALL,
)
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


def _has_top_level_comma(segment: str) -> bool:
    depth = 0
    in_single = False
    in_double = False

    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                return True
        i += 1

    return False


def _has_comma_join(sql_text: str) -> bool:
    return any(_has_top_level_comma(match.group(1)) for match in _FROM_CLAUSE_RE.finditer(sql_text))


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
    if any(fn in low for fn in _FORBIDDEN_FUNCTIONS):
        raise ValueError("Unsafe SQL detected.")
    if _has_comma_join(cleaned):
        raise ValueError("Comma joins are not allowed.")

    tables = _extract_tables(cleaned)
    lim = _extract_limit(cleaned)
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



