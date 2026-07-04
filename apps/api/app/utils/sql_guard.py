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
    "into",
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
    "readfile",
    "load_extension",
    "pg_read_file",
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)
_TOKEN_RE = re.compile(
    r'"[^"]+"|`[^`]+`|[a-z_][a-z0-9_]*|\d+|[(),.*]',
    re.IGNORECASE,
)
_CLAUSE_END_KEYWORDS = {"where", "group", "order", "limit", "having", "union", "except", "intersect"}


def _strip_sql(sql_text: str) -> str:
    return sql_text.strip().rstrip(";").strip()


def _normalize_ident(token: str) -> str:
    # Keep dots but strip quoting chars.
    t = token.strip()
    # remove trailing punctuation like "," or ")"
    t = t.rstrip(",)")
    # Strip common quoting.
    t = t.replace('"', "").replace("`", "")
    return t


def _tokenize(sql_text: str) -> list[str]:
    return [m.group(0) for m in _TOKEN_RE.finditer(sql_text)]


def _is_identifier_token(token: str) -> bool:
    return bool(
        token.startswith('"')
        or token.startswith("`")
        or re.fullmatch(r"[a-z_][a-z0-9_]*", token, flags=re.IGNORECASE)
    )


def _read_identifier(tokens: list[str], start: int) -> tuple[Optional[str], int]:
    if start >= len(tokens) or not _is_identifier_token(tokens[start]):
        return None, start

    parts = [tokens[start]]
    i = start + 1
    while i + 1 < len(tokens) and tokens[i] == "." and _is_identifier_token(tokens[i + 1]):
        parts.extend([tokens[i], tokens[i + 1]])
        i += 2
    return _normalize_ident("".join(parts)), i


def _extract_cte_names(tokens: list[str]) -> set[str]:
    if not tokens or tokens[0].lower() != "with":
        return set()

    names: set[str] = set()
    i = 1
    if i < len(tokens) and tokens[i].lower() == "recursive":
        i += 1

    while i < len(tokens):
        name, i = _read_identifier(tokens, i)
        if not name:
            break
        names.add(name)

        while i < len(tokens) and tokens[i].lower() != "as":
            i += 1
        if i >= len(tokens):
            break
        i += 1
        if i >= len(tokens) or tokens[i] != "(":
            break

        depth = 1
        i += 1
        while i < len(tokens) and depth:
            if tokens[i] == "(":
                depth += 1
            elif tokens[i] == ")":
                depth -= 1
            i += 1

        if i < len(tokens) and tokens[i] == ",":
            i += 1
            continue
        break
    return names


def _extract_tables(sql_text: str) -> set[str]:
    tokens = _tokenize(sql_text)
    cte_names = _extract_cte_names(tokens)
    tables: set[str] = set()
    depth = 0
    in_from_clause = False
    from_depth = 0
    i = 0

    while i < len(tokens):
        token = tokens[i]
        low = token.lower()

        if token == "(":
            depth += 1
            i += 1
            continue
        if token == ")":
            depth = max(0, depth - 1)
            if in_from_clause and depth < from_depth:
                in_from_clause = False
            i += 1
            continue

        if in_from_clause and depth == from_depth and low in _CLAUSE_END_KEYWORDS:
            in_from_clause = False

        if low in {"from", "join"}:
            in_from_clause = True
            from_depth = depth
            ident, next_i = _read_identifier(tokens, i + 1)
            if ident:
                tables.add(ident)
                i = next_i
                continue
        elif token == "," and in_from_clause and depth == from_depth:
            ident, next_i = _read_identifier(tokens, i + 1)
            if ident:
                tables.add(ident)
                i = next_i
                continue

        i += 1

    return tables - cte_names


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
    if any(fn in low for fn in _FORBIDDEN_FUNCTIONS):
        raise ValueError("Unsafe SQL detected.")

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



