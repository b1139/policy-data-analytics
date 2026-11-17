"""Analysis service orchestrator and background task runner."""

import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.core.database import async_session_factory
from app.llm.router import LLMRouter, get_llm_router
from app.schemas.analytics import (
    CorrelationResult,
    SectorShareResult,
    StatsResult,
    SummaryResult,
    TrendResult,
)
from app.schemas.report import AnalysisResult, ChartSpec, Citation
from app.services.pubsub import publish_step

logger = logging.getLogger(__name__)


def _format_time_label(val: Any) -> str:
    """Format time/year values into clean string labels (e.g., '2019' instead of '2019.0')."""
    if isinstance(val, (int, np.integer)):
        return str(val)
    if isinstance(val, (float, np.floating)):
        if np.isnan(val):
            return "NaN"
        if float(val).is_integer():
            return str(int(val))
        return f"{val:.2f}"
    s = str(val).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


class StatisticsEngine:
    """Deterministic statistical analysis engine for policy datasets."""

    @staticmethod
    def compute_trend(
        df: pd.DataFrame,
        value_col: str,
        time_col: str,
    ) -> TrendResult:
        """Compute linear regression trend and YoY percentage growth rates.

        Args:
            df: Input pandas DataFrame containing time series data.
            value_col: Name of the continuous metric column.
            time_col: Name of the temporal/year/date column.

        Returns:
            TrendResult with slope, intercept, r2, p_value, YoY growth rates,
            and overall_trend direction.
        """
        if df is None or df.empty or value_col not in df.columns or time_col not in df.columns:
            return TrendResult(
                error="insufficient_data",
                overall_trend="stable",
            )

        clean = df[[time_col, value_col]].dropna().copy()
        clean[value_col] = pd.to_numeric(clean[value_col], errors="coerce")
        clean = clean.dropna(subset=[value_col])

        if len(clean) < 3:
            return TrendResult(
                error="insufficient_data",
                overall_trend="stable",
            )

        # Sort chronologically by time_col
        time_num = pd.to_numeric(clean[time_col], errors="coerce")
        if time_num.notna().all() and time_num.nunique() > 1:
            clean["_sort_key"] = time_num
            clean = clean.sort_values(by="_sort_key").drop(columns=["_sort_key"])
            x = time_num.loc[clean.index].to_numpy(dtype=float)
        else:
            time_dt = pd.to_datetime(clean[time_col], errors="coerce")
            if time_dt.notna().all() and time_dt.nunique() > 1:
                clean["_sort_key"] = time_dt
                clean = clean.sort_values(by="_sort_key").drop(columns=["_sort_key"])
                x = np.arange(len(clean), dtype=float)
            else:
                clean = clean.sort_values(by=time_col)
                x = np.arange(len(clean), dtype=float)

        y = clean[value_col].to_numpy(dtype=float)

        # Compute linear regression
        if np.all(x == x[0]) or np.all(y == y[0]):
            slope = 0.0
            intercept = float(y[0])
            r2 = 0.0
            p_val = 1.0
        else:
            try:
                reg = stats.linregress(x, y)
                slope = float(reg.slope) if not np.isnan(reg.slope) else 0.0
                intercept = float(reg.intercept) if not np.isnan(reg.intercept) else 0.0
                r2 = float(reg.rvalue**2) if not np.isnan(reg.rvalue) else 0.0
                p_val = float(reg.pvalue) if not np.isnan(reg.pvalue) else 1.0
            except Exception as exc:
                logger.warning("linregress computation error: %s", exc)
                return TrendResult(
                    error="insufficient_data",
                    overall_trend="stable",
                )

        # Classify overall trend: slope sign + p_value < 0.05
        if p_val < 0.05 and slope > 0:
            overall_trend = "increasing"
        elif p_val < 0.05 and slope < 0:
            overall_trend = "decreasing"
        else:
            overall_trend = "stable"

        # Compute YoY growth rates
        yoy_growth: dict[str, float] = {}
        for i in range(1, len(clean)):
            prev_v = float(clean.iloc[i - 1][value_col])
            curr_v = float(clean.iloc[i][value_col])
            t_curr = _format_time_label(clean.iloc[i][time_col])
            pct = ((curr_v - prev_v) / abs(prev_v)) * 100.0 if prev_v != 0 else 0.0
            yoy_growth[t_curr] = round(float(pct), 2)

        return TrendResult(
            slope=round(slope, 4),
            intercept=round(intercept, 4),
            r2=round(r2, 4),
            p_value=round(p_val, 4),
            yoy_growth=yoy_growth,
            overall_trend=overall_trend,
        )

    @staticmethod
    def compute_summary_stats(
        df: pd.DataFrame,
        value_col: str,
    ) -> SummaryResult:
        """Compute descriptive summary statistics for a numerical series.

        Args:
            df: Input pandas DataFrame.
            value_col: Column name of continuous values.

        Returns:
            SummaryResult with mean, median, std, min, max, count, earliest_value,
            and latest_value.
        """
        if df is None or df.empty or value_col not in df.columns:
            return SummaryResult(
                count=0,
                error="insufficient_data",
            )

        s = pd.to_numeric(df[value_col].dropna(), errors="coerce").dropna()
        count = int(len(s))
        if count == 0:
            return SummaryResult(
                count=0,
                error="insufficient_data",
            )

        mean_val = float(s.mean())
        median_val = float(s.median())
        std_val = float(s.std(ddof=1)) if count > 1 else 0.0
        min_val = float(s.min())
        max_val = float(s.max())
        earliest_val = float(s.iloc[0])
        latest_val = float(s.iloc[-1])

        return SummaryResult(
            mean=round(mean_val, 4),
            median=round(median_val, 4),
            std=round(std_val, 4),
            min=round(min_val, 4),
            max=round(max_val, 4),
            count=count,
            earliest_value=round(earliest_val, 4),
            latest_value=round(latest_val, 4),
        )

    @staticmethod
    def compute_sector_share(
        df: pd.DataFrame,
        sector_col: str,
        value_col: str,
        year: int | str | None = None,
    ) -> SectorShareResult:
        """Compute sector percentage distribution for breakdown visualizations.

        Args:
            df: Input pandas DataFrame.
            sector_col: Column containing sector/category names.
            value_col: Column containing values to sum.
            year: Optional target year/period to filter by before computing shares.

        Returns:
            SectorShareResult with sector-to-percentage dictionary.
        """
        if df is None or df.empty or sector_col not in df.columns or value_col not in df.columns:
            return SectorShareResult(
                year=year,
                shares={},
                error="insufficient_data",
            )

        working_df = df.copy()

        # If a specific year is requested, filter on time/year column if found
        if year is not None:
            filtered = False
            for col in [
                "year",
                "Year",
                "YEAR",
                "period",
                "Period",
                "date",
                "Date",
                "time",
                "Time",
            ]:
                if col in working_df.columns:
                    match_mask = working_df[col].astype(str).str.strip() == str(year).strip()
                    if match_mask.any():
                        working_df = working_df[match_mask]
                        filtered = True
                        break

            if not filtered:
                # Look for matching column among non-sector/value columns
                for col in working_df.columns:
                    if col not in [sector_col, value_col]:
                        match_mask = working_df[col].astype(str).str.strip() == str(year).strip()
                        if match_mask.any():
                            working_df = working_df[match_mask]
                            filtered = True
                            break

        clean = working_df[[sector_col, value_col]].dropna().copy()
        clean[value_col] = pd.to_numeric(clean[value_col], errors="coerce")
        clean = clean.dropna(subset=[value_col])

        if clean.empty:
            return SectorShareResult(
                year=year,
                shares={},
                error="insufficient_data",
            )

        grouped = clean.groupby(sector_col)[value_col].sum()
        total = float(grouped.sum())

        if total > 0:
            shares = {str(k): round(float((v / total) * 100.0), 2) for k, v in grouped.items()}
        else:
            shares = {str(k): 0.0 for k in grouped.index}

        return SectorShareResult(
            year=year,
            shares=shares,
        )

    @staticmethod
    def compute_correlation(
        df: pd.DataFrame,
        col_a: str,
        col_b: str,
    ) -> CorrelationResult:
        """Compute Pearson and Spearman correlation coefficients with qualitative interpretation.

        Args:
            df: Input pandas DataFrame.
            col_a: First variable column name.
            col_b: Second variable column name.

        Returns:
            CorrelationResult containing pearson_r, spearman_r, p_value, and interpretation.
        """
        if df is None or df.empty or col_a not in df.columns or col_b not in df.columns:
            return CorrelationResult(
                interpretation="Insufficient data or missing columns for correlation analysis.",
                error="insufficient_data",
            )

        clean = df[[col_a, col_b]].dropna().copy()
        clean[col_a] = pd.to_numeric(clean[col_a], errors="coerce")
        clean[col_b] = pd.to_numeric(clean[col_b], errors="coerce")
        clean = clean.dropna()

        if len(clean) < 3:
            return CorrelationResult(
                interpretation="Insufficient data for correlation analysis (<3 valid observations).",
                error="insufficient_data",
            )

        a = clean[col_a].to_numpy(dtype=float)
        b = clean[col_b].to_numpy(dtype=float)

        if np.all(a == a[0]) or np.all(b == b[0]):
            return CorrelationResult(
                pearson_r=0.0,
                spearman_r=0.0,
                p_value=1.0,
                interpretation="No variation in one or both variables; correlation is undefined.",
            )

        try:
            p_res = stats.pearsonr(a, b)
            s_res = stats.spearmanr(a, b)

            pearson_r = float(p_res.statistic if hasattr(p_res, "statistic") else p_res[0])
            p_val = float(p_res.pvalue if hasattr(p_res, "pvalue") else p_res[1])
            spearman_r = float(s_res.statistic if hasattr(s_res, "statistic") else s_res[0])

            if np.isnan(pearson_r):
                pearson_r = 0.0
            if np.isnan(p_val):
                p_val = 1.0
            if np.isnan(spearman_r):
                spearman_r = 0.0
        except Exception as exc:
            logger.warning("Correlation computation error: %s", exc)
            return CorrelationResult(
                interpretation=f"Error computing correlation: {exc}",
                error="insufficient_data",
            )

        # Build qualitative policy-relevant interpretation
        abs_r = abs(pearson_r)
        if abs_r >= 0.8:
            strength = "Strong"
        elif abs_r >= 0.5:
            strength = "Moderate"
        elif abs_r >= 0.2:
            strength = "Weak"
        else:
            strength = "Negligible"

        if pearson_r > 0.05:
            direction = "positive"
        elif pearson_r < -0.05:
            direction = "negative"
        else:
            direction = "neutral"

        sig = (
            "statistically significant (p < 0.05)"
            if p_val < 0.05
            else "not statistically significant (p >= 0.05)"
        )
        interpretation = f"{strength} {direction} correlation (r={pearson_r:.2f}, {sig})."

        return CorrelationResult(
            pearson_r=round(pearson_r, 4),
            spearman_r=round(spearman_r, 4),
            p_value=round(p_val, 4),
            interpretation=interpretation,
        )

    @staticmethod
    def compute_comparison(
        df: pd.DataFrame,
        value_col: str,
        time_col: str,
        series_1_label: str | int,
        series_2_label: str | int,
        category_col: str | None = None,
    ) -> dict[str, Any]:
        """Compute structured comparative analytics between two periods or series.

        Args:
            df: Input DataFrame.
            value_col: Continuous metric column.
            time_col: Temporal/year column.
            series_1_label: First period/year label.
            series_2_label: Second period/year label.
            category_col: Optional sectoral/categorical column.

        Returns:
            Dictionary containing means, medians, delta, pct_change, and optional category breakdowns.
        """
        import re

        if df is None or df.empty or value_col not in df.columns or time_col not in df.columns:
            return {"error": "insufficient_data"}

        clean = df.copy()
        clean[value_col] = pd.to_numeric(clean[value_col], errors="coerce")
        clean = clean.dropna(subset=[value_col])
        clean[time_col] = clean[time_col].astype(str).str.strip()

        s1_str = str(series_1_label).strip()
        s2_str = str(series_2_label).strip()

        df_s1 = clean[
            clean[time_col].str.contains(rf"\b{re.escape(s1_str)}\b", regex=True, na=False)
        ]
        df_s2 = clean[
            clean[time_col].str.contains(rf"\b{re.escape(s2_str)}\b", regex=True, na=False)
        ]

        if df_s1.empty or df_s2.empty:
            return {
                "period_1": s1_str,
                "period_2": s2_str,
                "error": "one_or_both_periods_empty",
            }

        mean_1 = float(df_s1[value_col].mean())
        mean_2 = float(df_s2[value_col].mean())
        delta = round(mean_2 - mean_1, 4)
        pct_change = round((delta / abs(mean_1) * 100.0), 2) if mean_1 != 0 else None

        result: dict[str, Any] = {
            "period_1": s1_str,
            "period_2": s2_str,
            "metric": value_col,
            "series_1_mean": round(mean_1, 4),
            "series_2_mean": round(mean_2, 4),
            "series_1_min": round(float(df_s1[value_col].min()), 4),
            "series_2_min": round(float(df_s2[value_col].min()), 4),
            "series_1_max": round(float(df_s1[value_col].max()), 4),
            "series_2_max": round(float(df_s2[value_col].max()), 4),
            "absolute_difference": delta,
            "percentage_change": pct_change,
            "direction": "higher" if delta > 0 else ("lower" if delta < 0 else "unchanged"),
        }

        # If category_col is present, compute per-category comparison
        if category_col and category_col in clean.columns:
            try:
                combined_df = clean[clean[time_col].isin([s1_str, s2_str])]
                if not combined_df.empty:
                    piv = combined_df.pivot_table(
                        index=category_col,
                        columns=time_col,
                        values=value_col,
                        aggfunc="mean",
                    ).reset_index()

                    col_1 = [c for c in piv.columns if str(s1_str) in str(c)]
                    col_2 = [c for c in piv.columns if str(s2_str) in str(c)]

                    if col_1 and col_2:
                        cat_rows = []
                        for _, row in piv.iterrows():
                            c_name = str(row[category_col])
                            v1 = float(row[col_1[0]]) if pd.notna(row[col_1[0]]) else None
                            v2 = float(row[col_2[0]]) if pd.notna(row[col_2[0]]) else None
                            d_cat = (
                                round(v2 - v1, 4) if (v1 is not None and v2 is not None) else None
                            )
                            cat_rows.append(
                                {
                                    "category": c_name,
                                    s1_str: v1,
                                    s2_str: v2,
                                    "difference": d_cat,
                                }
                            )
                        result["by_category"] = cat_rows
            except Exception as exc:
                logger.warning("Error generating category breakdown for comparison: %s", exc)

        return result

    @classmethod
    def compute_statistics(
        cls,
        df: pd.DataFrame,
        value_col: str,
        time_col: str | None = None,
        sector_col: str | None = None,
        secondary_val_col: str | None = None,
        year: int | str | None = None,
        comparison: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StatsResult:
        """Consolidate descriptive, trend, sector share, and correlation analytics into a StatsResult.

        Args:
            df: Input DataFrame.
            value_col: Primary continuous value column.
            time_col: Optional column for trend regression and YoY calculation.
            sector_col: Optional column for sector distribution breakdown.
            secondary_val_col: Optional column for correlation against value_col.
            year: Optional filter year for sector distribution.
            metadata: Optional dictionary of context and dataset provenance.

        Returns:
            Aggregated StatsResult schema instance.
        """
        summary = cls.compute_summary_stats(df, value_col)

        trend = None
        if time_col and time_col in df.columns:
            trend = cls.compute_trend(df, value_col, time_col)

        sector_shares = None
        if sector_col and sector_col in df.columns:
            sector_shares = cls.compute_sector_share(df, sector_col, value_col, year=year)

        correlations = []
        if secondary_val_col and secondary_val_col in df.columns:
            corr = cls.compute_correlation(df, value_col, secondary_val_col)
            correlations.append(corr)

        return StatsResult(
            trend=trend,
            summary=summary,
            sector_shares=sector_shares,
            correlations=correlations,
            comparison=comparison,
            metadata=metadata or {},
        )


class _HybridInsightMethod:
    """Descriptor enabling generate_insights to be called either on an instance or the class."""

    def __init__(self, func: Any) -> None:
        self.func = func
        self.__doc__ = func.__doc__

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        target = instance if instance is not None else owner()

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.func(target, *args, **kwargs)

        return wrapper


class InsightGenerator:
    """LLM-powered insight narrative generator grounded in deterministic statistical outputs."""

    SYSTEM_PROMPT: str = (
        "Singapore policy analyst. Use ONLY the given stats; never invent numbers. "
        "Plain English, no jargon, short bullets."
    )

    OUTPUT_FORMAT: str = (
        "Markdown, exactly:\n"
        "**Answer:** 1 sentence.\n"
        "**Key Findings**\n- 3-5 bullets (<25 words, bold figure, dataset+year)\n"
        "**Policy Implications**\n- 2-3 bullets\n"
        "**Sources:** dataset names"
    )

    GROUNDING_INSTRUCTION: str = "Only use numbers from stats."

    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router

    @_HybridInsightMethod
    async def generate_insights(
        self,
        stats: StatsResult | dict[str, Any],
        query: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate policy narrative grounded in statistical analysis results with citation and fallback.

        Args:
            stats: Validated StatsResult or dictionary of statistical calculations.
            query: User's original research question or policy query.
            sources: List of metadata dictionaries representing underlying official datasets.

        Returns:
            A policy analysis insight string (150-400 words) with grounded statistics and citations.
        """
        stats_obj = StatsResult(**stats) if isinstance(stats, dict) else stats
        sources_list = sources or []

        # Format prompt payload
        sources_text = self._format_sources_for_prompt(sources_list)
        stats_dict = stats_obj.model_dump() if hasattr(stats_obj, "model_dump") else dict(stats_obj)
        stats_json = json.dumps(stats_dict, default=str, separators=(",", ":"))

        user_prompt = (
            f"Query: {query.strip()}\n"
            f"Sources:\n{sources_text}\n"
            f"Stats: {stats_json}\n"
            f"{self.OUTPUT_FORMAT}"
        )

        router = self.router or get_llm_router()
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await router.complete(
                messages=messages,
                temperature=0.3,
                max_tokens=450,
            )
            content = response.content.strip() if response and response.content else ""
            if content:
                return content
            logger.warning("LLM router returned empty response; falling back to template insight.")
        except Exception as exc:
            logger.warning(
                "LLM router completion failed (%s); falling back to template insight.", exc
            )

        return self._generate_fallback_insights(
            stats=stats_obj,
            query=query,
            sources=sources_list,
        )

    @classmethod
    def _format_sources_for_prompt(cls, sources: list[dict[str, Any]] | None) -> str:
        """Format list of data sources for structured LLM prompt inclusion."""
        if not sources:
            return "- Official Government Statistics (SingStat / Ministry of Manpower)"
        lines = []
        for s in sources:
            title = s.get("title") or s.get("name") or s.get("source") or "Official Dataset"
            period = s.get("period") or s.get("year") or s.get("date_range") or "Recent Years"
            publisher = (
                s.get("publisher")
                or s.get("agency")
                or s.get("source")
                or "Government of Singapore"
            )
            lines.append(f"- {title} ({period}) [Publisher: {publisher}]")
        return "\n".join(lines)

    @classmethod
    def _generate_fallback_insights(
        cls,
        stats: StatsResult,
        query: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> str:
        """Deterministic policy insight template used when LLM call fails or returns empty."""
        sources_list = sources or []
        if sources_list:
            source_names = [
                str(s.get("title") or s.get("name") or s.get("source") or "Official Dataset")
                for s in sources_list
            ]
            sources_str = ", ".join(source_names)
        else:
            sources_str = "official government statistics (SingStat and Ministry of Manpower)"

        clean_topic = query.strip().rstrip("?.!")
        topic = clean_topic if clean_topic else "key national policy and economic indicators"

        # Resolve date range
        date_range = "the analyzed reporting period"
        if sources_list:
            periods = [
                str(s.get("period") or s.get("year") or s.get("date_range"))
                for s in sources_list
                if (s.get("period") or s.get("year") or s.get("date_range"))
            ]
            if periods:
                date_range = periods[0]
        if date_range == "the analyzed reporting period" and stats.trend and stats.trend.yoy_growth:
            growth_keys = [str(k) for k in stats.trend.yoy_growth if str(k).strip()]
            if growth_keys:
                date_range = f"{growth_keys[0]} to {growth_keys[-1]}"
        elif (
            date_range == "the analyzed reporting period"
            and stats.sector_shares
            and stats.sector_shares.year
        ):
            date_range = str(stats.sector_shares.year)
        elif date_range == "the analyzed reporting period" and stats.metadata:
            meta_p = stats.metadata.get("period") or stats.metadata.get("year")
            if meta_p:
                date_range = str(meta_p)

        findings: list[str] = []
        if stats.trend and stats.trend.overall_trend and stats.trend.error is None:
            direction = str(stats.trend.overall_trend)
            verb = {"increasing": "rose", "decreasing": "fell"}.get(
                direction, "stayed broadly stable"
            )
            findings.append(f"**Trend:** the indicator {verb} over {date_range}.")
        if stats.summary and stats.summary.error is None and stats.summary.count > 0:
            sm = stats.summary
            if sm.earliest_value is not None and sm.latest_value is not None:
                findings.append(
                    f"**Start vs latest:** {sm.earliest_value:,.2f} → {sm.latest_value:,.2f}."
                )
            if sm.min is not None and sm.max is not None:
                findings.append(f"**Range:** low of {sm.min:,.2f}, high of {sm.max:,.2f}.")
            if sm.mean is not None:
                findings.append(f"**Average:** {sm.mean:,.2f} across {sm.count} observations.")
        if stats.sector_shares and stats.sector_shares.shares and stats.sector_shares.error is None:
            sorted_shares = sorted(
                stats.sector_shares.shares.items(), key=lambda kv: kv[1], reverse=True
            )
            top = ", ".join(f"{name} ({pct:.1f}%)" for name, pct in sorted_shares[:2])
            findings.append(f"**Largest share:** {top}.")
        for c in stats.correlations or []:
            if c.interpretation and c.error is None:
                findings.append(f"**Relationship:** {c.interpretation.rstrip('.')}.")

        if not findings:
            findings.append("**Data:** limited statistics were available for this query.")

        answer = f'Summary for "{topic}" based on official statistics from {sources_str}.'
        lines = [
            f"**Answer:** {answer}",
            "",
            "**Key Findings**",
            *[f"- {f}" for f in findings[:5]],
            "",
            "**Policy Implications**",
            "- Use these figures as a baseline when planning workforce and programme priorities.",
            "- Track the next release to confirm whether this pattern continues.",
            "",
            f"**Sources:** {sources_str}",
        ]
        return "\n".join(lines)


class ReportBuilder:
    """Assembles final validated AnalysisResult intelligence reports from analytics components."""

    @classmethod
    def build(
        cls,
        insights: str | list[str],
        charts: list[dict[str, Any] | ChartSpec] | None = None,
        stats: StatsResult | dict[str, Any] | None = None,
        datasets: list[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        """Assemble the complete AnalysisResult report structure.

        Args:
            insights: LLM-generated narrative or list of insight strings.
            charts: List of Plotly JSON dictionaries or ChartSpec instances.
            stats: Validated StatsResult or dictionary of statistical calculations.
            datasets: List of dataset records containing metadata for citation extraction.

        Returns:
            Validated AnalysisResult ready for JSON serialization and DB persistence.
        """
        # 1. Format insights narrative and preview
        if isinstance(insights, list):
            insights_text = "\n\n".join(str(i).strip() for i in insights if i)
        else:
            insights_text = str(insights or "").strip()

        truncated_preview = insights_text[:200]

        # 2. Format charts
        chart_specs: list[ChartSpec] = []
        if charts:
            for item in charts:
                if isinstance(item, ChartSpec):
                    chart_specs.append(item)
                elif isinstance(item, dict):
                    try:
                        chart_specs.append(ChartSpec.model_validate(item))
                    except Exception as exc:
                        logger.warning("Failed to validate chart spec: %s", exc)

        # 3. Extract citations from datasets metadata
        citations: list[Citation] = []
        seen_citations: set[tuple[str, str, str]] = set()

        if datasets:
            for d in datasets:
                if not isinstance(d, dict):
                    continue
                meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
                source = (
                    d.get("source")
                    or d.get("publisher")
                    or d.get("agency")
                    or meta.get("source")
                    or meta.get("publisher")
                    or meta.get("agency")
                    or "SingStat"
                )
                title = (
                    d.get("title")
                    or d.get("name")
                    or meta.get("title")
                    or meta.get("name")
                    or f"Official Dataset {d.get('dataset_id') or d.get('id') or ''}".strip()
                )
                url = (
                    d.get("url")
                    or d.get("source_url")
                    or meta.get("url")
                    or meta.get("source_url")
                    or None
                )
                d_id = str(
                    d.get("dataset_id")
                    or d.get("id")
                    or meta.get("dataset_id")
                    or meta.get("id")
                    or d.get("table_id")
                    or title
                )

                accessed_raw = (
                    d.get("accessed")
                    or meta.get("accessed")
                    or d.get("retrieved_at")
                    or meta.get("retrieved_at")
                )
                if isinstance(accessed_raw, datetime):
                    accessed_dt = accessed_raw
                elif isinstance(accessed_raw, str):
                    try:
                        accessed_dt = datetime.fromisoformat(accessed_raw)
                    except Exception:
                        accessed_dt = datetime.now(UTC)
                else:
                    accessed_dt = datetime.now(UTC)

                key = (str(source), d_id, str(title))
                if key not in seen_citations:
                    seen_citations.add(key)
                    citations.append(
                        Citation(
                            source=str(source),
                            title=str(title),
                            url=str(url) if url else None,
                            accessed=accessed_dt,
                            dataset_id=d_id,
                        )
                    )

        # Fallback if no citations extracted
        if not citations:
            citations.append(
                Citation(
                    source="Data not available",
                    title="Official Singapore Statistics",
                    url=None,
                    accessed=datetime.now(UTC),
                    dataset_id="unknown",
                )
            )

        # 4. Extract stats_summary (trend_direction, peak_year, overall_change_pct, data_points_count)
        stats_dict: dict[str, Any] = {}
        trend_obj: Any = None
        summary_obj: Any = None

        if isinstance(stats, StatsResult):
            stats_dict = stats.model_dump()
            trend_obj = stats.trend
            summary_obj = stats.summary
        elif isinstance(stats, dict):
            stats_dict = stats
            trend_obj = stats.get("trend")
            summary_obj = stats.get("summary")

        # Trend direction
        if stats_dict.get("trend_direction"):
            trend_direction = str(stats_dict["trend_direction"])
        elif trend_obj:
            if hasattr(trend_obj, "overall_trend") and trend_obj.overall_trend:
                trend_direction = str(trend_obj.overall_trend)
            elif isinstance(trend_obj, dict) and trend_obj.get("overall_trend"):
                trend_direction = str(trend_obj["overall_trend"])
            elif hasattr(trend_obj, "slope") and trend_obj.slope is not None:
                trend_direction = (
                    "increasing"
                    if trend_obj.slope > 0
                    else ("decreasing" if trend_obj.slope < 0 else "stable")
                )
            elif isinstance(trend_obj, dict) and trend_obj.get("slope") is not None:
                s = float(trend_obj["slope"])
                trend_direction = "increasing" if s > 0 else ("decreasing" if s < 0 else "stable")
            else:
                trend_direction = "stable"
        else:
            trend_direction = "stable"

        # Data points count
        if "data_points_count" in stats_dict and stats_dict["data_points_count"] is not None:
            data_points_count = int(stats_dict["data_points_count"])
        elif summary_obj:
            if hasattr(summary_obj, "count") and summary_obj.count is not None:
                data_points_count = int(summary_obj.count)
            elif isinstance(summary_obj, dict) and summary_obj.get("count") is not None:
                data_points_count = int(summary_obj["count"])
            else:
                data_points_count = 0
        else:
            data_points_count = 0

        # Overall change pct
        if "overall_change_pct" in stats_dict and stats_dict["overall_change_pct"] is not None:
            overall_change_pct = round(float(stats_dict["overall_change_pct"]), 2)
        elif summary_obj:
            earliest = (
                getattr(summary_obj, "earliest_value", None)
                if hasattr(summary_obj, "earliest_value")
                else (summary_obj.get("earliest_value") if isinstance(summary_obj, dict) else None)
            )
            latest = (
                getattr(summary_obj, "latest_value", None)
                if hasattr(summary_obj, "latest_value")
                else (summary_obj.get("latest_value") if isinstance(summary_obj, dict) else None)
            )
            if earliest is not None and latest is not None and earliest != 0:
                overall_change_pct = round(((latest - earliest) / abs(earliest)) * 100.0, 2)
            else:
                overall_change_pct = 0.0
        elif trend_obj:
            yoy = (
                getattr(trend_obj, "yoy_growth", None)
                if hasattr(trend_obj, "yoy_growth")
                else (trend_obj.get("yoy_growth") if isinstance(trend_obj, dict) else None)
            )
            if isinstance(yoy, dict) and yoy:
                overall_change_pct = round(float(list(yoy.values())[-1]), 2)
            else:
                overall_change_pct = 0.0
        else:
            overall_change_pct = 0.0

        # Peak year
        if "peak_year" in stats_dict and stats_dict["peak_year"] is not None:
            peak_year = stats_dict["peak_year"]
            with contextlib.suppress(ValueError, TypeError):
                peak_year = int(peak_year)
        else:
            yoy = (
                getattr(trend_obj, "yoy_growth", None)
                if hasattr(trend_obj, "yoy_growth")
                else (trend_obj.get("yoy_growth") if isinstance(trend_obj, dict) else None)
            )
            if isinstance(yoy, dict) and yoy:
                best_year, _ = max(yoy.items(), key=lambda kv: kv[1])
                try:
                    peak_year = int(best_year)
                except (ValueError, TypeError):
                    peak_year = str(best_year)
            elif (
                hasattr(stats, "sector_shares") and stats.sector_shares and stats.sector_shares.year
            ):
                peak_year = stats.sector_shares.year
            elif isinstance(stats_dict.get("sector_shares"), dict) and stats_dict[
                "sector_shares"
            ].get("year"):
                peak_year = stats_dict["sector_shares"]["year"]
            elif stats_dict.get("metadata", {}).get("year"):
                peak_year = stats_dict["metadata"]["year"]
            else:
                peak_year = None

        stats_summary = {
            "trend_direction": trend_direction,
            "peak_year": peak_year,
            "overall_change_pct": overall_change_pct,
            "data_points_count": data_points_count,
        }

        return AnalysisResult(
            insights=insights_text,
            charts=chart_specs,
            citations=citations,
            stats_summary=stats_summary,
            generated_at=datetime.now(UTC),
            truncated_preview=truncated_preview,
        )


class AnalysisService:
    """Service for coordinating analysis execution, persistence, and real-time events."""

    @staticmethod
    async def publish_step(
        analysis_id: uuid.UUID | str,
        step_dict: dict[str, Any],
    ) -> None:
        """Publish an agent execution step or status update to the pubsub bus.

        Args:
            analysis_id: UUID or string of the analysis pipeline.
            step_dict: Message dictionary conforming to LLD §7 format.
        """
        await publish_step(analysis_id, step_dict)

    @classmethod
    async def run_pipeline(cls, analysis_id: uuid.UUID | str) -> dict[str, Any]:
        """Execute asynchronous multi-agent policy data analysis pipeline.

        Transitions analysis status in the database, publishes status and step
        updates over the pubsub event channel, and invokes the multi-agent graph.

        Args:
            analysis_id: UUID or string of the persisted analysis record to process.
        """
        logger.info("Executing background analysis pipeline for analysis_id=%s", analysis_id)
        from app.agents.graph import run_analysis

        async with async_session_factory() as db:
            return await run_analysis(analysis_id=analysis_id, db=db)

    @classmethod
    async def resolve_failed_data(cls, analysis_id: uuid.UUID | str) -> dict[str, Any]:
        """Use LLM assistance to diagnose failed data retrieval and resolve by discovering alternative datasets.

        Employs the LLM router to inspect the failed query and attempted dataset parameters,
        determines appropriate search keywords or fallback official Singapore datasets,
        re-extracts data, and completes the analytics pipeline.

        Args:
            analysis_id: UUID or string of the failed analysis to resolve.

        Returns:
            dict[str, Any]: Completed analysis state or report.
        """
        logger.info("Starting AI-assisted data resolution for analysis_id=%s", analysis_id)
        from app.agents.graph import run_analysis
        from app.crud.analysis import get_analysis, update_analysis_status
        from app.llm.router import get_llm_router
        from app.schemas.analysis import AnalysisStatus
        from app.services.pubsub import format_status_change_message, publish_step

        uid = uuid.UUID(str(analysis_id)) if isinstance(analysis_id, str) else analysis_id
        async with async_session_factory() as db:
            analysis = await get_analysis(db, uid)
            if not analysis:
                raise ValueError(f"Analysis '{analysis_id}' not found.")

            query = analysis.query
            metadata = analysis.metadata_ or {}
            failed_data = (
                metadata.get("failed_data")
                or (analysis.result.get("failed_data") if analysis.result else {})
                or {}
            )

            # Publish event: Resolving data via LLM
            await publish_step(
                str(analysis_id),
                format_status_change_message(
                    analysis_id=str(analysis_id),
                    status=AnalysisStatus.RUNNING,
                    details={
                        "message": "AI is analyzing failure reason and discovering alternative official datasets to resolve data loading..."
                    },
                ),
            )

            # Prompt LLM to diagnose failure and suggest best matched keywords / dataset IDs
            router = get_llm_router()
            router.set_current_query(str(analysis_id))
            try:
                system_prompt = (
                    "You are an expert Singapore policy data engineer. "
                    "Analyze why data loading failed for the given policy inquiry and determine the best official Singapore statistics dataset keywords to retrieve matching data."
                )
                user_prompt = (
                    f"User Query: {query}\n"
                    f"Failed Data Details: {json.dumps(failed_data, default=str)}\n"
                    "Provide a JSON response with keys:\n"
                    "- diagnosis (str): short explanation of why previous retrieval failed\n"
                    "- resolved_keywords (str): clean keywords to query (e.g. 'cpi', 'employment', 'population', 'gdp')\n"
                    "- suggested_source (str): 'singstat' or 'mock_internal'\n"
                    "- recommended_table (str): descriptive title of the target table"
                )
                resolution_resp = await router.complete(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=400,
                    json_mode=True,
                )
                try:
                    res_plan = json.loads(resolution_resp.content)
                except Exception:
                    res_plan = {
                        "resolved_keywords": "singapore policy",
                        "suggested_source": "mock_internal",
                    }
            except Exception as llm_err:
                logger.warning(
                    "LLM data resolution prompt encountered error: %s. Using default resolution plan.",
                    llm_err,
                )
                res_plan = {"resolved_keywords": query, "suggested_source": "mock_internal"}

            # Update analysis record with resolution metadata
            updated_meta = {
                **metadata,
                "ai_resolution": res_plan,
                "resolved_at": datetime.now(UTC).isoformat(),
            }
            await update_analysis_status(
                db=db,
                id=uid,
                status=AnalysisStatus.RUNNING,
                metadata=updated_meta,
                error_msg=None,
            )

            # Re-run analysis pipeline with resolved data configuration
            import os

            os.environ["USE_MOCK_DATA_AS_FALLBACK"] = "true"

            # Execute run_analysis
            result = await run_analysis(analysis_id=uid, query=query, db=db)
            return result

    @classmethod
    def verify_hallucinations(
        cls,
        insights: str,
        datasets: list[dict[str, Any]] | None = None,
        stats: dict[str, Any] | Any | None = None,
    ) -> dict[str, Any]:
        """Audit policy insights for hallucinated sources, numeric drift, or unattributed claims.

        Args:
            insights: LLM-generated narrative insight.
            datasets: List of dataset metadata objects or dictionaries.
            stats: Computed statistics dictionary or StatsResult instance.

        Returns:
            Structured dictionary with citation_grounding, numeric_consistency,
            and source_attribution results.
        """
        from app.services.hallucination_detector import HallucinationDetector

        detector = HallucinationDetector()
        return detector.run_all_checks(
            insights=insights,
            datasets=datasets or [],
            stats=stats or {},
        )
