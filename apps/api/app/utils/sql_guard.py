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
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
)

_LIMIT_RE = re.compile(r"\blimit\b\s+(\d+)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)
_CLAUSE_TERMINATORS = {
    "where",
    "group",
    "order",
    "having",
    "limit",
    "offset",
    "fetch",
    "union",
    "except",
    "intersect",
}


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


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _matches_word(text: str, pos: int, word: str) -> bool:
    end = pos + len(word)
    if text[pos:end].lower() != word:
        return False
    before = pos == 0 or not _is_word_char(text[pos - 1])
    after = end >= len(text) or not _is_word_char(text[end])
    return before and after


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _skip_balanced_parentheses(text: str, pos: int) -> int:
    quote: Optional[str] = None
    depth = 0
    i = pos
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _read_identifier(text: str, pos: int) -> tuple[Optional[str], int]:
    pos = _skip_ws(text, pos)
    if pos >= len(text) or text[pos] == "(":
        return None, pos

    parts: list[str] = []
    while pos < len(text):
        ch = text[pos]
        if ch in ('"', "`"):
            quote = ch
            start = pos
            pos += 1
            while pos < len(text) and text[pos] != quote:
                pos += 1
            if pos < len(text):
                pos += 1
            parts.append(text[start:pos])
        else:
            start = pos
            while pos < len(text) and not text[pos].isspace() and text[pos] not in ",;()":
                pos += 1
            if start == pos:
                break
            parts.append(text[start:pos])

        dotted = _skip_ws(text, pos)
        if dotted < len(text) and text[dotted] == ".":
            parts.append(".")
            pos = _skip_ws(text, dotted + 1)
            continue
        break

    if not parts:
        return None, pos
    return "".join(parts), pos


def _extract_cte_names(sql_text: str) -> set[str]:
    if not sql_text.lower().startswith("with "):
        return set()

    names: set[str] = set()
    pos = _skip_ws(sql_text, len("with"))
    if _matches_word(sql_text, pos, "recursive"):
        pos = _skip_ws(sql_text, pos + len("recursive"))

    while pos < len(sql_text):
        raw_name, pos = _read_identifier(sql_text, pos)
        if not raw_name:
            break
        names.add(_normalize_ident(raw_name))

        pos = _skip_ws(sql_text, pos)
        if pos < len(sql_text) and sql_text[pos] == "(":
            pos = _skip_balanced_parentheses(sql_text, pos)
            pos = _skip_ws(sql_text, pos)

        if not _matches_word(sql_text, pos, "as"):
            break
        pos = _skip_ws(sql_text, pos + len("as"))
        if pos >= len(sql_text) or sql_text[pos] != "(":
            break
        pos = _skip_balanced_parentheses(sql_text, pos)
        pos = _skip_ws(sql_text, pos)

        if pos < len(sql_text) and sql_text[pos] == ",":
            pos = _skip_ws(sql_text, pos + 1)
            continue
        break

    return names


def _find_from_segment_end(sql_text: str, pos: int, base_depth: int) -> int:
    quote: Optional[str] = None
    depth = base_depth
    i = pos
    while i < len(sql_text):
        ch = sql_text[i]
        if quote:
            if ch == quote:
                if quote == "'" and i + 1 < len(sql_text) and sql_text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth < base_depth:
                return i
            i += 1
            continue
        if depth == base_depth:
            for word in _CLAUSE_TERMINATORS:
                if _matches_word(sql_text, i, word):
                    return i
        i += 1
    return i


def _iter_from_segments(sql_text: str) -> list[str]:
    segments: list[str] = []
    quote: Optional[str] = None
    depth = 0
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        if quote:
            if ch == quote:
                if quote == "'" and i + 1 < len(sql_text) and sql_text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue
        if _matches_word(sql_text, i, "from"):
            start = i + len("from")
            end = _find_from_segment_end(sql_text, start, depth)
            segments.append(sql_text[start:end])
            i = start
            continue
        i += 1
    return segments


def _segment_table_refs(segment: str) -> set[str]:
    refs: set[str] = set()
    raw, _ = _read_identifier(segment, 0)
    if raw:
        refs.add(_normalize_ident(raw))

    quote: Optional[str] = None
    depth = 0
    i = 0
    while i < len(segment):
        ch = segment[i]
        if quote:
            if ch == quote:
                if quote == "'" and i + 1 < len(segment) and segment[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue
        if depth == 0 and (ch == "," or _matches_word(segment, i, "join")):
            start = i + 1 if ch == "," else i + len("join")
            raw, _ = _read_identifier(segment, start)
            if raw:
                refs.add(_normalize_ident(raw))
        i += 1
    return refs


def _extract_tables(sql_text: str) -> set[str]:
    tables: set[str] = set()
    cte_names = _extract_cte_names(sql_text)
    for segment in _iter_from_segments(sql_text):
        for ident in _segment_table_refs(segment):
            if ident and ident not in cte_names:
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
    for fn in _FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{re.escape(fn)}\s*\(", low):
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
        if not tables:
            raise ValueError("Allowed table is required.")
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



