import io
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

MAX_ROWS_PER_SHEET = 50_000
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
STAGING_SCHEMA = "staging"


def _sanitize_token(raw: str, fallback: str = "col") -> str:
    t = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw).strip())
    t = t.strip("_") or fallback
    if t[0].isdigit():
        t = "t_" + t
    return t[:63].lower()


def _sanitize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign unique physical column names.

    Deduping only per sanitized base is not enough: a later column that
    sanitizes to `foo` becomes `foo_1`, which collides with an existing
    header already named `foo_1` (or `foo!` / `foo ` after sanitize).
    pandas then has duplicate labels and SQLAlchemy to_sql raises
    DuplicateColumnError, so Excel upload 500s and the DataSource stays
    stuck in status=staging.
    """
    out = df.copy()
    occupied: set[str] = set()
    new_cols: list[str] = []
    for col in out.columns:
        base = _sanitize_token(str(col), "col")
        name = base
        if name in occupied:
            i = 1
            while f"{base}_{i}" in occupied:
                i += 1
            name = f"{base}_{i}"
        occupied.add(name)
        new_cols.append(name)
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
        base = _sanitize_token(sheet, "sheet")
        slug = base
        if slug in occupied:
            i = 2
            while f"{base}_{i}" in occupied:
                i += 1
            slug = f"{base}_{i}"
        occupied.add(slug)
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

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{STAGING_SCHEMA}"'))

        for slug, (orig_name, df) in sheets.items():
            physical = f"{table_prefix}{slug}"
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
