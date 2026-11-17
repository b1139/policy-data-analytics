"""LangChain analysis tools for statistical calculation, chart generation, and grounded insight synthesis."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

import pandas as pd
from langchain_core.tools import StructuredTool, tool

from app.schemas.analytics import StatsResult
from app.services.analysis_service import InsightGenerator, StatisticsEngine
from app.services.visualization_service import VisualizationService

logger = logging.getLogger(__name__)


def _wrap_dual_callable(tool_obj: StructuredTool) -> StructuredTool:
    """Wrap a StructuredTool to support both direct function calling and LangChain .invoke()/.ainvoke()."""

    class DualCallableTool(StructuredTool):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            if self.coroutine:
                return self.coroutine(*args, **kwargs)
            if self.func:
                return self.func(*args, **kwargs)
            return super().__call__(*args, **kwargs)

    wrapped = DualCallableTool.from_function(
        func=tool_obj.func,
        coroutine=tool_obj.coroutine,
        name=tool_obj.name,
        description=tool_obj.description,
        args_schema=tool_obj.args_schema,
    )
    return wrapped


def _parse_dataframe(df_input: Any) -> pd.DataFrame:
    """Parse a DataFrame from JSON string, dictionary, list of dicts, or existing DataFrame."""
    if df_input is None:
        return pd.DataFrame()

    if isinstance(df_input, pd.DataFrame):
        return df_input.copy()

    if isinstance(df_input, list):
        try:
            return pd.DataFrame(df_input)
        except Exception:
            return pd.DataFrame()

    if isinstance(df_input, dict):
        if "columns" in df_input and "data" in df_input:
            try:
                return pd.DataFrame(data=df_input["data"], columns=df_input["columns"])
            except Exception:
                pass
        try:
            return pd.DataFrame(df_input)
        except Exception:
            return pd.DataFrame()

    if isinstance(df_input, str):
        cleaned = df_input.strip()
        if not cleaned:
            return pd.DataFrame()
        try:
            return pd.read_json(io.StringIO(cleaned), orient="split")
        except Exception:
            try:
                return pd.read_json(io.StringIO(cleaned))
            except Exception:
                pass
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "columns" in parsed and "data" in parsed:
                return pd.DataFrame(data=parsed["data"], columns=parsed["columns"])
            return pd.DataFrame(parsed)
        except Exception as exc:
            logger.warning("Could not parse DataFrame from input string: %s", exc)

    return pd.DataFrame()


def _detect_columns(
    df: pd.DataFrame,
    preferred_val: str | None = None,
    preferred_time: str | None = None,
    preferred_sector: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Auto-detect value, time, and sector column names from a DataFrame."""
    if df.empty:
        return None, None, None

    cols = list(df.columns)
    cols_lower = {str(c).lower(): str(c) for c in cols}

    # 1. Time column detection
    time_col = None
    if preferred_time and preferred_time in cols:
        time_col = preferred_time
    else:
        for candidate in ["year", "date", "period", "quarter", "month", "time", "financial_year"]:
            if candidate in cols_lower:
                time_col = cols_lower[candidate]
                break

    # 2. Value column detection
    val_col = None
    if preferred_val and preferred_val in cols:
        val_col = preferred_val
    else:
        for candidate in [
            "value",
            "val",
            "metric",
            "amount",
            "headcount",
            "employment",
            "median_wage",
            "gross_wage",
            "unemployment_rate",
            "gdp",
            "gdp_growth",
            "nominal_gdp",
            "real_gdp",
        ]:
            if candidate in cols_lower and cols_lower[candidate] != time_col:
                val_col = cols_lower[candidate]
                break

    if not val_col:
        for c in cols:
            if c == time_col:
                continue
            numeric_vals = pd.to_numeric(df[c], errors="coerce")
            if numeric_vals.notna().sum() > 0:
                val_col = c
                break

    if not val_col:
        non_time = [c for c in cols if c != time_col]
        if non_time:
            val_col = non_time[0]

    # 3. Sector column detection
    sector_col = None
    if preferred_sector and preferred_sector in cols:
        sector_col = preferred_sector
    else:
        for candidate in ["sector", "industry", "category", "economic_sector", "group", "type"]:
            if candidate in cols_lower and cols_lower[candidate] not in [time_col, val_col]:
                sector_col = cols_lower[candidate]
                break

    return val_col, time_col, sector_col


def filter_dataframe_by_query(
    df: pd.DataFrame,
    query: str = "",
    preferred_val: str | None = None,
    preferred_time: str | None = None,
    preferred_sector: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filter a DataFrame and detect query-aligned columns strictly based on the user query.

    Ensures that when a user asks e.g. 'compare employment growth 2025 vs 2026',
    the DataFrame is filtered strictly using Pandas to only 2025 and 2026,
    the specific metric asked for (e.g. yoy_change_pct/growth rather than generic headcount)
    is selected, and analytics stats/visualizations are computed exclusively on the user-requested scope.
    """
    if df.empty:
        return df, {
            "filter_applied": False,
            "val_col": None,
            "time_col": None,
            "category_col": None,
            "is_comparison": False,
            "comparison_years": None,
            "target_years": [],
        }

    q = (query or "").strip()
    q_lower = q.lower()
    cols = list(df.columns)
    cols_lower = {str(c).lower(): str(c) for c in cols}

    # 1. Detect Time Column
    time_col = None
    if preferred_time and preferred_time in cols:
        time_col = preferred_time
    else:
        for candidate in ["year", "date", "period", "quarter", "month", "time", "financial_year"]:
            if candidate in cols_lower:
                time_col = cols_lower[candidate]
                break

    # 2. Detect Category / Sector Column
    sector_col = None
    if preferred_sector and preferred_sector in cols:
        sector_col = preferred_sector
    else:
        for candidate in [
            "sector",
            "industry",
            "category",
            "economic_sector",
            "occupation",
            "group",
            "type",
        ]:
            if candidate in cols_lower and cols_lower[candidate] != time_col:
                sector_col = cols_lower[candidate]
                break

    # 3. Detect Value / Metric Column with Query Intent Sensitivity
    val_col = None
    if preferred_val and preferred_val in cols:
        val_col = preferred_val
    else:
        is_growth_query = any(
            k in q_lower
            for k in ("growth", "change", "pct", "percent", "percentage", "yoy", "rate")
        )
        is_headcount_query = any(
            k in q_lower
            for k in ("headcount", "count", "level", "workers", "number", "total", "workforce")
        )
        is_wage_query = any(
            k in q_lower for k in ("wage", "wages", "salary", "income", "earning", "compensation")
        )

        growth_candidates = [
            "yoy_change_pct",
            "yoy_growth",
            "growth_rate",
            "pct_growth",
            "pct_change",
            "yoy_change",
            "growth",
            "unemployment_rate",
            "rate",
        ]
        headcount_candidates = [
            "employment_count",
            "headcount",
            "total_workforce",
            "ict_headcount",
            "count",
            "value",
            "val",
        ]
        wage_candidates = [
            "median_gross_wage",
            "gross_wage",
            "median_wage",
            "median_gross_monthly_wage",
            "wages",
            "income",
        ]

        priority_candidates = []
        if is_growth_query:
            priority_candidates.extend(growth_candidates)
        if is_headcount_query:
            priority_candidates.extend(headcount_candidates)
        if is_wage_query:
            priority_candidates.extend(wage_candidates)

        priority_candidates.extend(
            [
                "value",
                "val",
                "metric",
                "amount",
                "headcount",
                "employment",
                "employment_count",
                "median_wage",
                "gross_wage",
                "unemployment_rate",
                "gdp",
                "gdp_growth",
                "nominal_gdp",
                "real_gdp",
            ]
        )

        for cand in priority_candidates:
            if cand in cols_lower and cols_lower[cand] not in [time_col, sector_col]:
                val_col = cols_lower[cand]
                break

        if not val_col:
            for c in cols:
                if c in [time_col, sector_col]:
                    continue
                num_s = pd.to_numeric(df[c], errors="coerce")
                if num_s.notna().sum() > 0:
                    val_col = c
                    break

        if not val_col:
            rem = [c for c in cols if c not in [time_col, sector_col]]
            val_col = rem[0] if rem else cols[0]

    # 4. Extract Query Targets (Years, Comparison, Range, Category)
    found_years = re.findall(r"\b(19\d\d|20\d\d)\b", q)
    unique_years: list[str] = []
    for y in found_years:
        if y not in unique_years:
            unique_years.append(y)

    range_match = re.search(
        r"\b(?:between|from)\s+(19\d\d|20\d\d)\s+(?:and|to)\s+(19\d\d|20\d\d)\b", q_lower
    )
    is_range = bool(range_match)
    range_years = (int(range_match.group(1)), int(range_match.group(2))) if range_match else None

    is_comparison = bool(
        any(k in q_lower for k in ("vs", "versus", "compare", "comparison", "difference", "delta"))
        or len(unique_years) >= 2
    )
    comp_years = (unique_years[-2], unique_years[-1]) if len(unique_years) >= 2 else None

    # 5. Apply Pandas Filtering
    filtered_df = df.copy()
    filter_applied = False

    # A. Sector Filter (if user specifically asked for a specific sector like "manufacturing")
    sector_filtered_val = None
    if sector_col and sector_col in filtered_df.columns:
        unique_cats = filtered_df[sector_col].dropna().unique()
        for cat_val in unique_cats:
            cat_str = str(cat_val).lower()
            if len(cat_str) > 3 and cat_str in q_lower:
                match_mask = filtered_df[sector_col].astype(str).str.lower() == cat_str
                if match_mask.any():
                    filtered_df = filtered_df[match_mask]
                    sector_filtered_val = str(cat_val)
                    filter_applied = True
                    break

    # B. Time Filter (a requested period absent from the data means "no data")
    period_missing = False
    if time_col and time_col in filtered_df.columns:
        time_str = filtered_df[time_col].astype(str)
        t_mask = None
        if is_range and range_years:
            min_y, max_y = min(range_years), max(range_years)
            num_t = pd.to_numeric(filtered_df[time_col], errors="coerce")
            if num_t.notna().any():
                t_mask = (num_t >= min_y) & (num_t <= max_y)
        elif is_comparison and comp_years:
            y1, y2 = comp_years
            pat = rf"\b(?:{re.escape(str(y1))}|{re.escape(str(y2))})\b"
            t_mask = time_str.str.contains(pat, regex=True, na=False)
        elif unique_years:
            pat = "|".join([rf"\b{re.escape(str(y))}\b" for y in unique_years])
            t_mask = time_str.str.contains(pat, regex=True, na=False)

        if t_mask is not None:
            if t_mask.any():
                filtered_df = filtered_df[t_mask]
                filter_applied = True
            else:
                period_missing = True
                filtered_df = filtered_df.iloc[0:0]

    if val_col == "yoy_change_pct":
        metric_label = "YoY Employment Growth (%)"
    elif val_col == "yoy_growth":
        metric_label = "YoY Growth (%)"
    elif val_col == "employment_count":
        metric_label = "Employment Headcount ('000)"
    else:
        metric_label = (val_col or "Value").replace("_", " ").title()

    meta = {
        "filter_applied": filter_applied,
        "is_comparison": is_comparison,
        "comparison_years": comp_years,
        "is_range": is_range,
        "range_years": range_years,
        "target_years": unique_years,
        "time_col": time_col,
        "category_col": sector_col,
        "val_col": val_col,
        "metric_label": metric_label,
        "sector_filtered": sector_filtered_val,
        "original_row_count": len(df),
        "filtered_row_count": len(filtered_df),
        "no_match": period_missing,
    }

    return filtered_df, meta


@tool
def _compute_statistics_impl(
    df_json: Any = None,
    data: Any = None,
    query: str | None = None,
    analysis_type: str = "all",
    value_col: str | None = None,
    time_col: str | None = None,
    sector_col: str | None = None,
) -> dict[str, Any]:
    """Execute deterministic statistical analytics (trend, summary, sector shares, correlation, comparison).

    Args:
        df_json: Serialized DataFrame JSON string, dictionary, or DataFrame representation.
        data: Alias for df_json.
        query: Optional user prompt query to filter DataFrame strictly to requested period/sectors/metrics.
        analysis_type: Type of analysis ('all', 'trend', 'summary', 'sector_share', 'correlation').
        value_col: Optional column name for metric values.
        time_col: Optional column name for temporal values.
        sector_col: Optional column name for sectoral/categorical values.

    Returns:
        Dictionary containing computed statistical calculations conforming to StatsResult.
    """
    try:
        raw_input = data if data is not None else df_json
        raw_df = _parse_dataframe(raw_input)
        if raw_df.empty:
            return {
                "error": "empty_dataframe",
                "message": "No data available to compute statistics.",
            }

        query_meta: dict[str, Any] = {}
        if query:
            df, query_meta = filter_dataframe_by_query(
                raw_df,
                query=query,
                preferred_val=value_col,
                preferred_time=time_col,
                preferred_sector=sector_col,
            )
            if df.empty:
                return {
                    "error": "no_data",
                    "message": "No data available for the period or scope requested in the query.",
                }
            v_col = value_col or query_meta.get("val_col")
            t_col = time_col or query_meta.get("time_col")
            s_col = sector_col or query_meta.get("category_col")
        else:
            df = raw_df
            det_val, det_time, det_sector = _detect_columns(
                df,
                preferred_val=value_col,
                preferred_time=time_col,
                preferred_sector=sector_col,
            )
            v_col = det_val or (df.columns[0] if len(df.columns) > 0 else "")
            t_col = det_time
            s_col = det_sector

        v_col = v_col or (df.columns[0] if len(df.columns) > 0 else "")
        at = (analysis_type or "all").lower().strip()

        if at == "trend":
            if not t_col:
                t_col = df.columns[0]
            trend_res = StatisticsEngine.compute_trend(df, v_col, t_col)
            return {"trend": trend_res.model_dump()}

        if at == "summary":
            summary_res = StatisticsEngine.compute_summary_stats(df, v_col)
            return {"summary": summary_res.model_dump()}

        if at == "sector_share":
            if not s_col:
                s_cols = [c for c in df.columns if c != v_col and c != t_col]
                s_col = s_cols[0] if s_cols else v_col
            shares_res = StatisticsEngine.compute_sector_share(df, s_col, v_col)
            return {"sector_shares": shares_res.model_dump()}

        comparison_res = None
        if query_meta.get("is_comparison") and query_meta.get("comparison_years") and t_col:
            y1, y2 = query_meta["comparison_years"]
            comparison_res = StatisticsEngine.compute_comparison(
                df=df,
                value_col=v_col,
                time_col=t_col,
                series_1_label=y1,
                series_2_label=y2,
                category_col=s_col,
            )

        metadata_payload = {
            "value_col": v_col,
            "time_col": t_col,
            "sector_col": s_col,
            "row_count": len(df),
            "original_row_count": len(raw_df),
            "filter_applied": query_meta.get("filter_applied", False),
            "target_years": query_meta.get("target_years", []),
        }

        stats_obj = StatisticsEngine.compute_statistics(
            df=df,
            value_col=v_col,
            time_col=t_col,
            sector_col=s_col,
            comparison=comparison_res,
            metadata=metadata_payload,
        )
        return stats_obj.model_dump()

    except Exception as exc:
        logger.exception("compute_statistics tool error: %s", exc)
        return {"error": "computation_failed", "details": str(exc)}


compute_statistics = _wrap_dual_callable(_compute_statistics_impl)


@tool
def _generate_chart_impl(
    data: Any = None,
    df_json: Any = None,
    chart_type: str = "line",
    title: str = "Policy Trend",
    source_label: str = "Official Singapore Statistics",
    x_col: str | None = None,
    y_col: str | list[str] | None = None,
    y_cols: list[str] | None = None,
    orientation: str = "v",
    color: str | None = None,
) -> dict[str, Any]:
    """Generate an interactive Plotly chart specification dictionary.

    Args:
        data: Serialized DataFrame JSON string, dictionary, records list, or DataFrame.
        df_json: Alias for data parameter.
        chart_type: Chart type ('line', 'bar', 'multi_line', 'heatmap').
        title: Title of the chart.
        source_label: Source attribution label for bottom-right citation.
        x_col: Column name for X axis.
        y_col: Column name or list of column names for Y axis.
        y_cols: Alias for multiple Y columns in multi-line charts.
        orientation: Orientation for bar chart ('v' or 'h').
        color: Optional hex color override.

    Returns:
        Plotly chart specification dictionary with 'data' and 'layout'.
    """
    try:
        raw_input = data if data is not None else df_json
        df = _parse_dataframe(raw_input)
        if df.empty:
            return {"error": "no_data", "type": "empty_chart"}

        ctype = (chart_type or "line").lower().strip()

        # Handle heatmap
        if ctype == "heatmap":
            return VisualizationService.heatmap(
                df=df,
                title=title,
                source_label=source_label,
            )

        # Detect columns if not specified
        det_val, det_time, det_sector = _detect_columns(
            df,
            preferred_val=y_col if isinstance(y_col, str) else None,
            preferred_time=x_col,
            preferred_sector=x_col if ctype == "bar" else None,
        )

        target_x = x_col or det_time or det_sector or df.columns[0]

        # Multi-line chart handling
        if (
            ctype in ["multi_line", "multiline", "multi-line"]
            or y_cols
            or (isinstance(y_col, list) and len(y_col) > 1)
        ):
            if y_cols:
                target_y_cols = y_cols
            elif isinstance(y_col, list):
                target_y_cols = y_col
            elif isinstance(y_col, str):
                target_y_cols = [y_col]
            else:
                target_y_cols = [c for c in df.columns if c != target_x]

            return VisualizationService.multi_line_chart(
                df=df,
                x_col=target_x,
                y_cols=target_y_cols,
                title=title,
                source_label=source_label,
            )

        target_y = (
            y_col
            if isinstance(y_col, str)
            else det_val or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
        )

        if ctype == "bar":
            return VisualizationService.bar_chart(
                df=df,
                x_col=target_x,
                y_col=target_y,
                title=title,
                source_label=source_label,
                orientation=orientation,
                color=color,
            )

        # Default: line chart
        return VisualizationService.line_chart(
            df=df,
            x_col=target_x,
            y_col=target_y,
            title=title,
            source_label=source_label,
            color=color,
        )

    except Exception as exc:
        logger.exception("generate_chart tool error: %s", exc)
        return {
            "error": "chart_generation_failed",
            "type": "empty_chart",
            "title": title,
            "details": str(exc),
        }


generate_chart = _wrap_dual_callable(_generate_chart_impl)


@tool
async def generate_insight(
    query: str = "",
    stats: Any = None,
    sources: list[dict[str, Any]] | str | None = None,
    stats_dict: Any = None,
) -> str:
    """Generate LLM-powered Singapore policy insights grounded in statistical analysis results.

    Args:
        query: User policy research inquiry.
        stats: Statistical results schema, dictionary, or serialized JSON string.
        sources: Metadata list of underlying official datasets, periods, and publishers.
        stats_dict: Alias for stats parameter for backward compatibility.

    Returns:
        Structured policy narrative (150-400 words) with grounded statistics and citations.
    """
    raw_stats = stats if stats is not None else stats_dict
    try:
        stats_raw = json.loads(raw_stats) if isinstance(raw_stats, str) else raw_stats

        if isinstance(stats_raw, dict):
            stats_obj = StatsResult(**stats_raw)
        elif isinstance(stats_raw, StatsResult):
            stats_obj = stats_raw
        else:
            stats_obj = StatsResult()

        sources_list = json.loads(sources) if isinstance(sources, str) else sources or []

        generator = InsightGenerator()
        return await generator.generate_insights(
            stats=stats_obj,
            query=query,
            sources=sources_list,
        )
    except Exception as exc:
        logger.error("generate_insight tool encountered an error: %s", exc, exc_info=True)
        generator = InsightGenerator()
        fallback_stats = raw_stats if isinstance(raw_stats, StatsResult) else StatsResult()
        return generator._generate_fallback_insights(
            stats=fallback_stats,
            query=query,
            sources=sources if isinstance(sources, list) else [],
        )


__all__ = [
    "compute_statistics",
    "generate_chart",
    "generate_insight",
    "filter_dataframe_by_query",
]
