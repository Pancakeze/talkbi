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
    "sqlite_sleep",
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_IDENT_PART = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[a-z_][a-z0-9_$]*)'
_IDENT_RE = rf"{_IDENT_PART}(?:\s*\.\s*{_IDENT_PART})*"
_FROM_CLAUSE_RE = re.compile(
    r"\bfrom\b\s+(.+?)(?=\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\bhaving\b|\blimit\b|\bunion\b|\bintersect\b|\bexcept\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_JOIN_RE = re.compile(rf"\bjoin\b\s+({_IDENT_RE})", re.IGNORECASE)
_IDENT_AT_START_RE = re.compile(rf"\s*({_IDENT_RE})", re.IGNORECASE)
_CTE_NAME_RE = re.compile(rf"(?:\bwith\b\s+(?:recursive\s+)?|,)\s*({_IDENT_PART})\s+as\s*\(", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)


def _strip_sql(sql_text: str) -> str:
    return sql_text.strip().rstrip(";").strip()


def _normalize_ident(token: str) -> str:
    # Keep dots but strip quoting chars.
    t = token.strip()
    # remove trailing punctuation like "," or ")"
    t = t.rstrip(",")
    t = re.sub(r"\s*\.\s*", ".", t)
    # Strip common quoting.
    t = t.replace('"', "").replace("`", "").replace("[", "").replace("]", "")
    return t


def _split_top_level_commas(sql_text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        if quote:
            if ch == quote:
                # SQL escapes quotes by doubling them; keep scanning inside the quoted token.
                if i + 1 < len(sql_text) and sql_text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "[":
            quote = "]"
        elif ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(sql_text[start:i])
            start = i + 1
        i += 1
    parts.append(sql_text[start:])
    return parts


def _extract_cte_names(sql_text: str) -> set[str]:
    return {_normalize_ident(raw) for raw in _CTE_NAME_RE.findall(sql_text)}


def _first_table_identifier(segment: str) -> str | None:
    segment = segment.strip()
    if not segment or segment.startswith("("):
        return None
    match = _IDENT_AT_START_RE.match(segment)
    if not match:
        return None
    return _normalize_ident(match.group(1))


def _extract_tables(sql_text: str) -> set[str]:
    tables: set[str] = set()
    cte_names = _extract_cte_names(sql_text)
    for from_clause in _FROM_CLAUSE_RE.findall(sql_text):
        for segment in _split_top_level_commas(from_clause):
            ident = _first_table_identifier(segment)
            if ident and ident not in cte_names:
                tables.add(ident)
    for raw in _JOIN_RE.findall(sql_text):
        ident = _normalize_ident(raw)
        if ident not in cte_names:
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
    if any(fn in low for fn in _FORBIDDEN_FUNCTIONS):
        raise ValueError("Unsafe SQL detected.")

    tables = _extract_tables(cleaned)
    lim = _extract_limit(cleaned)
    if policy.allowed_tables is not None and not tables:
        raise ValueError("A query against an allowed table is required.")
    if tables:
        if lim is None:
            raise ValueError("LIMIT clause is required.")
        if lim > policy.max_limit:
            raise ValueError("LIMIT is too large.")
    if policy.allowed_tables is not None:
        norm_allowed = frozenset(_normalize_ident(t) for t in policy.allowed_tables)
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



