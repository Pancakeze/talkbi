import logging
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models import DataSource, ThemeField, ThemeLibrary, User
from app.schemas.chat import ChatQueryResponse
from app.services.ollama_client import OllamaConfig, ollama_generate
from app.utils.sql_guard import SQLGuardPolicy, validate_sql

logger = logging.getLogger(__name__)

_NUMERIC_HINTS = ("int", "float", "double", "decimal", "number")
_SERVER_STAGING_SCHEMA = "staging"
_SERVER_STAGING_TABLE_RE = re.compile(r"^ds_\d+_[a-z0-9_]+$")


def _is_numeric_dtype(dtype_str: str) -> bool:
    s = (dtype_str or "").lower()
    return any(x in s for x in _NUMERIC_HINTS)


def _normalize_identifier(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace('"', "").replace("`", "").strip()


def _is_server_generated_staging_table(ds: DataSource, table_meta: object) -> bool:
    if ds.source_type != "excel" or not isinstance(table_meta, dict):
        return False

    table = table_meta.get("table")
    if not isinstance(table, str):
        return False
    expected_prefix = f"ds_{ds.id}_"
    if not table.startswith(expected_prefix) or not _SERVER_STAGING_TABLE_RE.fullmatch(table):
        return False

    schema = table_meta.get("schema")
    qualified = _normalize_identifier(table_meta.get("qualified"))
    if schema == _SERVER_STAGING_SCHEMA:
        return qualified == f"{_SERVER_STAGING_SCHEMA}.{table}"
    if schema is None:
        return qualified == table
    return False


def _build_baseline_sql(prompt: str, *, qualified: str, columns: list[dict], limit: int = 100) -> str:
    """
    Deterministic SQL baseline from prompt + column dtypes.
    Works even when LLM output is poor.
    """
    p = (prompt or "").strip()
    # pick candidates
    numeric_cols = [c["name"] for c in columns if _is_numeric_dtype(str(c.get("dtype", ""))) and c.get("name")]
    non_numeric_cols = [c["name"] for c in columns if not _is_numeric_dtype(str(c.get("dtype", ""))) and c.get("name")]

    # intent heuristics (Chinese)
    lowp = p.lower()
    wants_count = any(k in p for k in ("数量", "总数", "次数")) or "count" in lowp
    wants_avg = any(k in p for k in ("平均", "求平均")) or "avg" in lowp or "average" in lowp
    wants_sum = any(k in p for k in ("总和", "合计", "累计", "总计", "求和")) or "sum" in lowp
    wants_group = any(k in p for k in ("各", "按", "分别", "分", "每"))

    group_col = non_numeric_cols[0] if non_numeric_cols else None
    value_col = numeric_cols[0] if numeric_cols else None

    # If user asks "汇总/统计", prefer SUM on numeric columns when possible.
    wants_summary = any(k in p for k in ("汇总", "统计"))

    if wants_group and group_col:
        if wants_avg and value_col:
            agg = f'AVG("{value_col}") AS value'
        elif wants_sum and value_col:
            agg = f'SUM("{value_col}") AS value'
        elif (wants_summary or wants_count) and value_col:
            agg = f'SUM("{value_col}") AS value'
        elif wants_summary or wants_count:
            agg = "COUNT(*) AS value"
        elif value_col:
            agg = f'SUM("{value_col}") AS value'
        else:
            agg = "COUNT(*) AS value"
        return f'SELECT "{group_col}" AS category, {agg} FROM {qualified} GROUP BY "{group_col}" LIMIT {limit}'

    # no group: single KPI
    if wants_avg:
        if value_col:
            return f'SELECT AVG("{value_col}") AS value FROM {qualified} LIMIT 1'
        # No numeric columns detected; fall back to COUNT(*) rather than a meaningless preview.
        return f"SELECT COUNT(*) AS value FROM {qualified} LIMIT 1"
    if wants_sum:
        if value_col:
            return f'SELECT SUM("{value_col}") AS value FROM {qualified} LIMIT 1'
        # No numeric columns detected; fall back to COUNT(*) rather than a meaningless preview.
        return f"SELECT COUNT(*) AS value FROM {qualified} LIMIT 1"
    if wants_summary and value_col:
        return f'SELECT SUM("{value_col}") AS value FROM {qualified} LIMIT 1'
    if wants_summary or wants_count:
        return f"SELECT COUNT(*) AS value FROM {qualified} LIMIT 1"

    # fallback: preview a few columns
    cols = [c.get("name") for c in columns if c.get("name")]
    cols = [c for c in cols if isinstance(c, str)][: min(5, len(cols))]
    col_sql = ", ".join(f'"{c}"' for c in cols) or "*"
    return f"SELECT {col_sql} FROM {qualified} LIMIT {limit}"


def _looks_like_aggregate(prompt: str, sql_text: str) -> bool:
    """Best-effort: if prompt asks for counting/summing/avg, require aggregate or GROUP BY."""
    p = (prompt or "")
    lowp = p.lower()
    wants = any(k in p for k in ("数量", "总数", "次数", "汇总", "统计", "平均", "求平均", "合计", "总和", "累计", "总计", "求和")) or any(
        k in lowp for k in ("count", "sum", "avg", "average")
    )
    if not wants:
        return True
    low = (sql_text or "").lower()
    return any(fn in low for fn in ("count(", "sum(", "avg(", "group by"))


def _wants_aggregate(prompt: str) -> bool:
    p = (prompt or "")
    lowp = p.lower()
    return any(k in p for k in ("数量", "总数", "次数", "汇总", "统计", "平均", "求平均", "合计", "总和", "累计", "总计", "求和")) or any(
        k in lowp for k in ("count", "sum", "avg", "average")
    )


def _sanitize_llm_sql(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
    # remove a leading "sql" marker
    if s.lower().startswith("sql"):
        s = s[3:].strip()
    # strip any trailing code fences
    s = re.sub(r"```$", "", s).strip()
    return s

def generate_sql_from_prompt(prompt: str, theme_ids: list[int]) -> str:
    if "相关" in prompt or "散点" in prompt:
        return (
            "SELECT district_name, AVG(congestion_index) AS avg_index, "
            "COUNT(accident_id) AS accident_count "
            "FROM traffic_flow_monthly GROUP BY district_name LIMIT 20"
        )
    return (
        "SELECT district_name, AVG(congestion_index) AS avg_index "
        "FROM traffic_flow_monthly GROUP BY district_name LIMIT 20"
    )


def build_chart_spec(prompt: str) -> dict:
    chart_type = "scatter" if ("相关" in prompt or "散点" in prompt) else "bar"
    if chart_type == "scatter":
        return {
            "chartType": chart_type,
            "title": "AI 生成图表",
            "xField": "avg_index",
            "yField": "accident_count",
            "series": [{"name": "分析结果"}],
        }
    return {
        "chartType": chart_type,
        "title": "AI 生成图表",
        "xField": "district_name",
        "yField": "avg_index",
        "series": [{"name": "分析结果"}],
    }


def _mock_rows(prompt: str) -> list[dict]:
    base = [
        {"district_name": "朝阳区", "avg_index": 3.8, "accident_count": 320},
        {"district_name": "海淀区", "avg_index": 3.5, "accident_count": 250},
        {"district_name": "丰台区", "avg_index": 2.8, "accident_count": 180},
        {"district_name": "西城区", "avg_index": 2.1, "accident_count": 110},
    ]
    if "相关" in prompt or "散点" in prompt:
        return base
    return [{k: v for k, v in row.items() if k != "accident_count"} for row in base]


def _mock_response(prompt: str) -> ChatQueryResponse:
    sql_text = generate_sql_from_prompt(prompt, [])
    validate_sql(sql_text)
    chart_spec = build_chart_spec(prompt)
    rows = _mock_rows(prompt)
    return ChatQueryResponse(
        sql=sql_text,
        chart_spec=chart_spec,
        rows=rows,
        explanation="（MOCK）未命中主题库 staging 表查询，返回演示数据。",
    )


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _chart_from_rows(prompt: str, rows: list[dict]) -> dict:
    scatter = "相关" in prompt or "散点" in prompt
    if not rows:
        return {
            "chartType": "bar",
            "title": "AI 生成图表",
            "xField": "x",
            "yField": "y",
            "series": [{"name": "分析结果"}],
        }
    sample = rows[0]
    keys = list(sample.keys())
    numeric = [k for k in keys if _is_number(sample.get(k))]
    categorical = [k for k in keys if k not in numeric]
    if scatter and len(numeric) >= 2:
        return {
            "chartType": "scatter",
            "title": "AI 生成图表",
            "xField": numeric[0],
            "yField": numeric[1],
            "series": [{"name": "分析结果"}],
        }
    if categorical and numeric:
        return {
            "chartType": "bar",
            "title": "AI 生成图表",
            "xField": categorical[0],
            "yField": numeric[0],
            "series": [{"name": "分析结果"}],
        }
    if len(numeric) >= 2:
        return {
            "chartType": "bar",
            "title": "AI 生成图表",
            "xField": keys[0],
            "yField": keys[1],
            "series": [{"name": "分析结果"}],
        }
    return {
        "chartType": "bar",
        "title": "AI 生成图表",
        "xField": keys[0],
        "yField": keys[1] if len(keys) > 1 else keys[0],
        "series": [{"name": "分析结果"}],
    }


def _try_staging_query(
    db: Session,
    user: User,
    prompt: str,
    theme_ids: list[int],
) -> Optional[ChatQueryResponse]:
    if not theme_ids:
        return None

    for tid in theme_ids:
        theme = (
            db.query(ThemeLibrary)
            .filter(ThemeLibrary.id == tid, ThemeLibrary.owner_id == user.id)
            .first()
        )
        if not theme or not theme.data_source_id:
            continue

        ds = (
            db.query(DataSource)
            .filter(
                DataSource.id == theme.data_source_id,
                DataSource.owner_id == user.id,
            )
            .first()
        )
        if not ds or not isinstance(ds.connection_info, dict):
            continue

        staging = ds.connection_info.get("staging") or {}
        tables_meta_list = [
            t
            for t in (staging.get("tables") or [])
            if _is_server_generated_staging_table(ds, t)
        ]
        if not tables_meta_list:
            continue

        tables_by_name = {t["table"]: t for t in tables_meta_list}
        fields = (
            db.query(ThemeField)
            .filter(ThemeField.theme_id == theme.id)
            .order_by(ThemeField.id)
            .all()
        )
        visible = [f for f in fields if f.visible]
        if not visible:
            continue

        by_table: dict[str, list[ThemeField]] = {}
        for f in visible:
            by_table.setdefault(f.table_name, []).append(f)

        chosen_table = None
        chosen_cols: list[str] = []
        for tname, flist in by_table.items():
            meta = tables_by_name.get(tname)
            if not meta:
                continue
            allowed_meta = {c["name"] for c in meta.get("columns", [])}
            cols = [f.field_name for f in flist if f.field_name in allowed_meta]
            if cols:
                chosen_table = tname
                chosen_cols = cols
                break

        if not chosen_table:
            first = tables_meta_list[0]
            if isinstance(first, dict) and first.get("table") and first.get("columns"):
                chosen_table = str(first["table"])
                chosen_cols = [
                    c.get("name")
                    for c in (first.get("columns") or [])
                    if isinstance(c, dict) and c.get("name")
                ]
                chosen_cols = [c for c in chosen_cols if isinstance(c, str)][:5]
            if not chosen_table or not chosen_cols:
                continue

        meta = tables_by_name[chosen_table]
        qualified = meta["qualified"]
        columns_meta = meta.get("columns") or []
        if not isinstance(columns_meta, list):
            columns_meta = []
        allowed_tables = frozenset(
            (t.get("qualified") or "").replace('"', "").replace("`", "")
            for t in tables_meta_list
            if isinstance(t, dict)
        )
        col_sql = ", ".join(f'"{c}"' for c in chosen_cols)
        sql_text = f"SELECT {col_sql} FROM {qualified} LIMIT 100"

        baseline_sql = _build_baseline_sql(prompt, qualified=qualified, columns=columns_meta, limit=100)
        used_llm_sql = False

        if not settings.llm_mock_mode:
            allowed_cols = ", ".join(chosen_cols)
            llm_prompt = (
                "You are a SQL generator for analytics.\n"
                "Return ONLY one SQL query. No markdown, no explanation.\n"
                "Hard rules:\n"
                "- Only SELECT (or WITH ... SELECT)\n"
                "- Must include LIMIT <= 200\n"
                "- Only use this table: {qualified}\n"
                "- Only use these columns: {allowed_cols}\n"
                "- Do not use comments, semicolons, or DDL/DML.\n"
                "- If user asks for summary/statistics, use COUNT/SUM/AVG and GROUP BY when appropriate.\n"
                "\n"
                "User question (Chinese): {user_prompt}\n"
                "Suggested baseline SQL (you may improve but keep rules): {baseline_sql}\n"
                "\n"
                "Output SQL only.\n"
            ).format(
                qualified=qualified,
                allowed_cols=allowed_cols,
                user_prompt=prompt,
                baseline_sql=baseline_sql,
            )
            try:
                raw = ollama_generate(
                    cfg=OllamaConfig(
                        base_url=settings.ollama_base_url,
                        model=settings.ollama_model,
                        timeout_s=90.0,
                    ),
                    prompt=llm_prompt,
                )
                sql_text = _sanitize_llm_sql(raw)
                used_llm_sql = True
                if _wants_aggregate(prompt) and not _looks_like_aggregate(prompt, sql_text):
                    logger.warning("LLM SQL does not match aggregate intent; fallback to baseline SQL.")
                    sql_text = baseline_sql
                    used_llm_sql = False
            except Exception as exc:
                logger.warning("Ollama SQL generation failed, fallback to simple SELECT: %s", exc)
                sql_text = baseline_sql
                used_llm_sql = False
        try:
            validate_sql(
                sql_text,
                policy=SQLGuardPolicy(
                    max_limit=200,
                    allowed_schemas=("staging",),
                    allowed_tables=allowed_tables,
                ),
            )
        except ValueError as exc:
            logger.warning("SQLGuard rejected staging SQL for theme %s: %s", theme.id, exc)
            continue

        try:
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SET LOCAL statement_timeout = 3000"))
                result = conn.execute(text(sql_text))
                rows = [dict(row._mapping) for row in result]
        except Exception as exc:
            logger.warning(
                "Staging query failed for theme %s table %s: %s",
                theme.id,
                chosen_table,
                exc,
            )
            continue

        chart_spec = _chart_from_rows(prompt, rows)
        return ChatQueryResponse(
            sql=sql_text,
            chart_spec=chart_spec,
            rows=rows,
            explanation=(
                "已基于 Excel 落地表与主题库字段执行查询。"
                + ("（Ollama 生成 SQL）" if used_llm_sql else "")
            ),
        )

    return None


def run_chat_query(
    db: Session,
    user: User,
    prompt: str,
    theme_ids: list[int],
) -> ChatQueryResponse:
    logger.info(
        "chat_query user=%s theme_ids=%s llm_mock_mode=%s ollama_model=%s",
        user.username,
        theme_ids,
        settings.llm_mock_mode,
        settings.ollama_model,
    )
    staged = _try_staging_query(db, user, prompt, theme_ids)
    if staged:
        return staged
    logger.info("chat_query fallback_to_mock user=%s theme_ids=%s", user.username, theme_ids)
    return _mock_response(prompt)
