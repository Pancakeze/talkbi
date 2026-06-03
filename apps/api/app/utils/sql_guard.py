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
    "create",
    "replace",
    "grant",
    "revoke",
    "into",
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
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(r"\b(from|join)\b", re.IGNORECASE)
_IDENT_PART = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[a-z_][a-z0-9_$]*)'
_IDENT_RE = re.compile(rf"{_IDENT_PART}(?:\s*\.\s*{_IDENT_PART})*", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)
_SOURCE_STOP_WORDS = {
    "where",
    "join",
    "left",
    "right",
    "full",
    "inner",
    "outer",
    "cross",
    "on",
    "group",
    "order",
    "having",
    "limit",
    "offset",
    "union",
    "except",
    "intersect",
    "window",
}


def _strip_sql(sql_text: str) -> str:
    return sql_text.strip().rstrip(";").strip()


def _normalize_ident(token: str) -> str:
    # Keep dots but strip quoting chars.
    t = token.strip()
    # remove trailing punctuation like "," or ")"
    t = t.rstrip(",")
    # Strip common quoting.
    t = t.replace('"', "").replace("`", "").replace("[", "").replace("]", "")
    t = re.sub(r"\s*\.\s*", ".", t)
    return t


def _skip_ws(sql_text: str, pos: int) -> int:
    while pos < len(sql_text) and sql_text[pos].isspace():
        pos += 1
    return pos


def _consume_balanced_parens(sql_text: str, pos: int) -> int:
    depth = 0
    quote: str | None = None
    while pos < len(sql_text):
        ch = sql_text[pos]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "'" and quote == "'" and pos + 1 < len(sql_text) and sql_text[pos + 1] == "'":
                pos += 1
        elif ch in {"'", '"', "`"}:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return pos


def _consume_identifier(sql_text: str, pos: int) -> tuple[str | None, int]:
    pos = _skip_ws(sql_text, pos)
    m = _IDENT_RE.match(sql_text, pos)
    if not m:
        return None, pos
    ident = _normalize_ident(m.group(0))
    if ident.lower() in _SOURCE_STOP_WORDS:
        return None, pos
    return ident, m.end()


def _consume_alias(sql_text: str, pos: int) -> int:
    pos = _skip_ws(sql_text, pos)
    if sql_text[pos : pos + 1] == ",":
        return pos

    m = _WORD_RE.match(sql_text, pos)
    if not m:
        return pos
    word = m.group(0).lower()
    if word in _SOURCE_STOP_WORDS:
        return pos
    if word == "as":
        alias, alias_end = _consume_identifier(sql_text, m.end())
        return alias_end if alias else pos
    return m.end()


def _extract_tables(sql_text: str) -> set[str]:
    tables: set[str] = set()
    for match in _FROM_JOIN_RE.finditer(sql_text):
        source_kind = match.group(1).lower()
        pos = match.end()
        while True:
            pos = _skip_ws(sql_text, pos)
            if pos >= len(sql_text):
                break

            if sql_text[pos] == "(":
                # The scanner will find table references inside subqueries separately.
                pos = _consume_balanced_parens(sql_text, pos)
                pos = _consume_alias(sql_text, pos)
            else:
                ident, next_pos = _consume_identifier(sql_text, pos)
                if not ident:
                    break
                tables.add(ident)
                pos = _consume_alias(sql_text, next_pos)

            pos = _skip_ws(sql_text, pos)
            if source_kind == "from" and pos < len(sql_text) and sql_text[pos] == ",":
                pos += 1
                continue
            break
    return tables


def _extract_top_level_limit(sql_text: str) -> Optional[int]:
    depth = 0
    quote: str | None = None
    pos = 0
    while pos < len(sql_text):
        ch = sql_text[pos]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "'" and quote == "'" and pos + 1 < len(sql_text) and sql_text[pos + 1] == "'":
                pos += 1
        elif ch in {"'", '"', "`"}:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            m = _LIMIT_RE.match(sql_text, pos)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return None
        pos += 1
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
    if any(fn in low for fn in _FORBIDDEN_FUNCTIONS):
        raise ValueError("Unsafe SQL detected.")

    tables = _extract_tables(cleaned)
    lim = _extract_top_level_limit(cleaned)
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



