import io
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

MAX_ROWS_PER_SHEET = 50_000
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
STAGING_SCHEMA = "staging"
# PostgreSQL NAMEDATALEN-1. Longer names are rejected by SQLAlchemy's PG
# dialect or silently truncated by the server, colliding with a sibling
# identifier (DuplicateColumn / DuplicateTable / IdentifierError).
MAX_SQL_IDENT_LEN = 63


def _sanitize_token(raw: str, fallback: str = "col") -> str:
    t = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw).strip())
    t = t.strip("_") or fallback
    if t[0].isdigit():
        t = "t_" + t
    return t[:MAX_SQL_IDENT_LEN].lower()


def _unique_sql_ident(
    base: str,
    occupied: set[str],
    *,
    max_len: int = MAX_SQL_IDENT_LEN,
) -> str:
    """Return a unique identifier that fits in max_len characters.

    Suffixes must be included in the budget: a 63-char base that collides
    cannot become base+'_1' (65 chars). PostgreSQL would truncate that
    back to 63 and recreate the collision the occupied set just avoided.
    """
    raw = (base or "col")[:max_len] or "col"
    name = raw
    i = 1
    while name in occupied:
        suffix = f"_{i}"
        keep = max(1, max_len - len(suffix))
        name = raw[:keep] + suffix
        i += 1
    occupied.add(name)
    return name


def _sanitize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign unique physical column names.

    Deduping only per sanitized base is not enough: a later column that
    sanitizes to `foo` becomes `foo_1`, which collides with an existing
    header already named `foo_1` (or `foo!` / `foo ` after sanitize).
    pandas then has duplicate labels and SQLAlchemy to_sql raises
    DuplicateColumnError, so Excel upload 500s and the DataSource stays
    stuck in status=staging.

    Names must also stay within MAX_SQL_IDENT_LEN so PostgreSQL does not
    truncate `aaa…aaa_1` back onto `aaa…aaa`.
    """
    out = df.copy()
    occupied: set[str] = set()
    new_cols: list[str] = []
    for col in out.columns:
        base = _sanitize_token(str(col), "col")
        new_cols.append(_unique_sql_ident(base, occupied))
    out.columns = new_cols
    return out


def _load_sheet_dataframes(file_bytes: bytes, filename: str) -> dict[str, tuple[str, pd.DataFrame]]:
    """
    Returns dict slug -> (original_sheet_name, dataframe).
    slug is used as the physical table suffix (stable, unique).
    """
    name = (filename or "upload").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_ROWS_PER_SHEET)
        df = _sanitize_dataframe_columns(df)
        slug = _sanitize_token(Path(filename or "data").stem, "sheet")
        return {slug: ((filename or "data").rsplit(".", 1)[0], df)}

    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    occupied: set[str] = set()
    result: dict[str, tuple[str, pd.DataFrame]] = {}
    for sheet in excel.sheet_names:
        slug = _unique_sql_ident(_sanitize_token(sheet, "sheet"), occupied)
        df = excel.parse(sheet, nrows=MAX_ROWS_PER_SHEET)
        df = _sanitize_dataframe_columns(df)
        result[slug] = (sheet, df)
    return result


def _preview_from_sheets(sheets: dict[str, tuple[str, pd.DataFrame]]) -> list[dict]:
    preview = []
    for slug, (orig_name, df) in sheets.items():
        preview.append(
            {
                "sheet_name": orig_name,
                "table_slug": slug,
                "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns.tolist()],
                "sample_rows": min(len(df), 50),
                "row_count": int(len(df)),
            }
        )
    return preview


def materialize_excel_staging(
    engine: Engine,
    data_source_id: int,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Load Excel/CSV into DB staging tables; return connection_info payload
    (filename, sheets preview, staging metadata for SQL and UI).
    """
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("File too large.")

    sheets = _load_sheet_dataframes(file_bytes, filename)
    if not sheets:
        raise ValueError("No sheets found in workbook.")

    dialect = engine.dialect.name
    table_prefix = f"ds_{data_source_id}_"
    staging_tables: list[dict] = []
    occupied_physical: set[str] = set()

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{STAGING_SCHEMA}"'))

        for slug, (orig_name, df) in sheets.items():
            # Prefix + slug can exceed NAMEDATALEN (long CSV stems, large ids).
            physical = _unique_sql_ident(f"{table_prefix}{slug}", occupied_physical)
            if dialect == "postgresql":
                qualified = f'"{STAGING_SCHEMA}"."{physical}"'
                df.to_sql(
                    physical,
                    conn,
                    schema=STAGING_SCHEMA,
                    if_exists="replace",
                    index=False,
                    chunksize=500,
                    method="multi",
                )
            else:
                qualified = f'"{physical}"'
                df.to_sql(physical, conn, if_exists="replace", index=False, chunksize=500)

            staging_tables.append(
                {
                    "sheet_name": orig_name,
                    "table": physical,
                    "schema": STAGING_SCHEMA if dialect == "postgresql" else None,
                    "qualified": qualified,
                    "row_count": int(len(df)),
                    "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns.tolist()],
                }
            )

    return {
        "filename": filename,
        "sheets": _preview_from_sheets(sheets),
        "staging": {
            "dialect": dialect,
            "schema": STAGING_SCHEMA if dialect == "postgresql" else None,
            "tables": staging_tables,
        },
    }
