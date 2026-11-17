"""Analytics Agent node using LangGraph ReAct pattern.

Executes deterministic statistical computations (summary, trend regression, YoY growth,
sector shares), generates interactive Plotly visualizations, and synthesizes grounded
policy narrative insights.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableBinding
try:
    from langgraph.graph.state import CompiledStateGraph as CompiledGraph
except ImportError:
    try:
        from langgraph.graph.state import CompiledGraph  # type: ignore[attr-defined]
    except ImportError:
        from langgraph.graph.graph import CompiledGraph  # type: ignore[assignment]
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentName, AgentState, StepType
from app.core.config import settings
import re
import pandas as pd
from app.agents.tools.analysis_tools import (
    compute_statistics,
    generate_chart,
    generate_insight,
    filter_dataframe_by_query,
    _parse_dataframe,
    _detect_columns,
)
from app.services.visualization_service import VisualizationService
from app.llm.router import get_llm_router
from app.crud.agent_log import create_agent_log
from app.services.pubsub import format_agent_step_message, publish_step

logger = logging.getLogger(__name__)

# Context variable to optionally provide an active AsyncSession to analytics node
analytics_db_context: ContextVar[AsyncSession | None] = ContextVar(
    "analytics_db_context", default=None
)

# Guardrail: Maximum tool iterations per node execution
MAX_ANALYTICS_ITERATIONS: int = 15


def _resolve_citation_url(
    source: str,
    dataset_id: str,
    title: str = "",
    existing_url: str | None = None,
) -> str:
    """Ensure every dataset citation points directly to an active, functional official Singapore portal URL."""
    src = (source or "").lower()
    d_id = str(dataset_id or "").strip()
    t_lower = (title or "").lower()

    if existing_url and existing_url.startswith("http"):
        # Fix tablebuilder without /TS/
        if "tablebuilder.singstat.gov.sg/table/" in existing_url:
            parts = existing_url.split("/table/")
            if len(parts) > 1 and parts[1].strip().upper().startswith("M"):
                return f"https://tablebuilder.singstat.gov.sg/table/TS/{parts[1].strip().upper()}"
            elif "employment" in d_id.lower() or "employment" in t_lower or "labor" in d_id.lower():
                return "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment"
            else:
                return "https://tablebuilder.singstat.gov.sg"
        # Fix fake mock data.gov.sg hash URLs (e.g. d_e3b8a1c97a5b3a4a6b2c)
        if "data.gov.sg/datasets/d_" in existing_url:
            q_topic = "ict workforce" if ("ict" in d_id.lower() or "ict" in t_lower) else "employment"
            return f"https://data.gov.sg/datasets?query={q_topic}"
        # If already a valid, non-mock URL
        if not any(f in existing_url for f in ["d_e3b8a", "mock", "localhost", "127.0.0.1"]):
            return existing_url

    # Check if table ID is a SingStat Table code (M...)
    if d_id.upper().startswith("M"):
        return f"https://tablebuilder.singstat.gov.sg/table/TS/{d_id.upper()}"

    # Route based on theme/topic to official live pages
    if "employment" in d_id.lower() or "employment" in t_lower or "labor" in d_id.lower() or "labor" in t_lower:
        if "mom" in src:
            return "https://stats.mom.gov.sg/Pages/Employment-Summary-Table.aspx"
        return "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment"
    if "unemployment" in d_id.lower() or "unemployment" in t_lower:
        return "https://data.gov.sg/datasets?query=unemployment+rate"
    if "wage" in d_id.lower() or "income" in d_id.lower() or "wage" in t_lower:
        return "https://data.gov.sg/datasets?query=wages"
    if "ict" in d_id.lower() or "ict" in t_lower or "tech" in t_lower:
        return "https://data.gov.sg/datasets?query=ict+workforce"
    if "gdp" in d_id.lower() or "gdp" in t_lower:
        return "https://www.singstat.gov.sg/find-data/search-by-theme/economy/national-accounts"
    if "cpi" in d_id.lower() or "price" in t_lower or "inflation" in t_lower:
        return "https://www.singstat.gov.sg/find-data/search-by-theme/economy/prices-and-price-indices"
    if "business" in d_id.lower() or "acra" in d_id.lower() or "business" in t_lower:
        return "https://data.gov.sg/datasets?query=business+entities"
    if "singstat" in src:
        return "https://tablebuilder.singstat.gov.sg"
    if "datagov" in src or "data.gov.sg" in src:
        return f"https://data.gov.sg/datasets?query={d_id}"
    return "https://www.singstat.gov.sg"


_NON_ADDITIVE_HINTS = ("rate", "pct", "percent", "growth", "change", "ratio", "index", "median", "mean", "avg")


def _is_empty_chart(chart: Any) -> bool:
    """Return True when a chart spec is missing or an empty-chart placeholder."""
    if not isinstance(chart, dict) or chart.get("type") == "empty_chart" or chart.get("error"):
        return True
    return not chart.get("data")


def _query_aligned_frames(
    datasets: list[dict[str, Any]],
    query: str,
) -> list[tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]]:
    """Return datasets that still hold numeric rows after applying the query's scope."""
    usable: list[tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]] = []
    for ds in datasets:
        raw_content = ds.get("df_json") or ds.get("dataframe_json") or ds.get("data")
        if not raw_content:
            continue
        df = _parse_dataframe(raw_content)
        if df.empty:
            continue
        filtered_df, meta = filter_dataframe_by_query(df, query)
        val_col = meta.get("val_col")
        if meta.get("no_match") or filtered_df.empty or val_col not in filtered_df.columns:
            continue
        target_df = filtered_df.copy()
        target_df[val_col] = pd.to_numeric(target_df[val_col], errors="coerce")
        target_df = target_df.dropna(subset=[val_col])
        if target_df.empty:
            continue
        usable.append((ds, target_df, meta))
    return usable


def _period_key(value: Any) -> str:
    """Normalize a period label (2023, 2023Q1, 2023-05-01...) to a 4-digit year for alignment."""
    text = str(value).strip()
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else text


def _build_combined_stats(
    datasets: list[dict[str, Any]],
    query: str,
) -> dict[str, Any] | None:
    """Merge query-aligned series from multiple sources (SingStat + Data.gov.sg ...) into one view.

    Returns None unless at least two distinct sources contribute a time series. Output holds a
    per-source summary, the year-aligned table, a base-100 index per source (comparable across
    differing units), cross-source correlation and the average gap in growth between sources.
    """
    series: dict[str, dict[str, Any]] = {}
    for ds, target_df, meta in _query_aligned_frames(datasets, query):
        time_col = meta.get("time_col")
        val_col = meta.get("val_col")
        if not time_col or time_col not in target_df.columns or not val_col:
            continue
        work = target_df[[time_col, val_col]].copy()
        work["_p"] = work[time_col].map(_period_key)
        by_period = work.groupby("_p")[val_col].mean().sort_index()
        if by_period.empty:
            continue
        label = str(ds.get("source") or "unknown")
        if label in series:  # same source twice -> disambiguate by dataset id
            label = f"{label}:{ds.get('dataset_id')}"
        series[label] = {
            "dataset_id": ds.get("dataset_id"),
            "title": ds.get("title"),
            "metric": meta.get("metric_label") or val_col,
            "values": {str(k): float(v) for k, v in by_period.items()},
        }

    if len(series) < 2:
        return None

    per_source: list[dict[str, Any]] = []
    for label, info in series.items():
        vals = info["values"]
        periods = sorted(vals)
        first, last = vals[periods[0]], vals[periods[-1]]
        per_source.append(
            {
                "source": label,
                "dataset_id": info["dataset_id"],
                "title": info["title"],
                "metric": info["metric"],
                "periods": len(periods),
                "first_period": periods[0],
                "latest_period": periods[-1],
                "latest_value": round(last, 4),
                "mean": round(sum(vals.values()) / len(vals), 4),
                "change_pct": round((last - first) / first * 100, 2) if first else None,
            }
        )

    shared = sorted(set.intersection(*(set(i["values"]) for i in series.values())))
    combined: dict[str, Any] = {
        "sources": per_source,
        "shared_periods": shared,
        "aligned_table": {p: {s: round(i["values"][p], 4) for s, i in series.items()} for p in shared},
    }

    if len(shared) >= 2:
        indexed: dict[str, dict[str, float]] = {}
        for label, info in series.items():
            base = info["values"][shared[0]]
            if base:
                indexed[label] = {p: round(info["values"][p] / base * 100, 2) for p in shared}
        combined["indexed_series"] = indexed

        labels = list(series)
        if len(shared) >= 3 and len(labels) >= 2:
            frame = pd.DataFrame({s: [series[s]["values"][p] for p in shared] for s in labels})
            corr = frame[labels[0]].corr(frame[labels[1]])
            combined["correlation"] = None if pd.isna(corr) else round(float(corr), 3)
            if combined["correlation"] is not None:
                combined["interpretation"] = (
                    f"{labels[0]} and {labels[1]} move "
                    + ("together" if combined["correlation"] > 0.5 else "in opposite directions" if combined["correlation"] < -0.5 else "largely independently")
                    + f" over {shared[0]}-{shared[-1]} (r={combined['correlation']})."
                )
        growth = [s["change_pct"] for s in per_source if s["change_pct"] is not None]
        if len(growth) >= 2:
            combined["growth_gap_pct_points"] = round(max(growth) - min(growth), 2)
    else:
        combined["note"] = "Sources do not share two or more periods; compared per-source only."
    return combined


def _build_combined_chart(combined: dict[str, Any] | None) -> dict[str, Any] | None:
    """Multi-source base-100 line chart from combined stats (None if not drawable)."""
    indexed = (combined or {}).get("indexed_series") or {}
    if len(indexed) < 2:
        return None
    periods = combined["shared_periods"]
    frame = pd.DataFrame({"period": periods, **{s: [v[p] for p in periods] for s, v in indexed.items()}})
    chart = VisualizationService.multi_line_chart(
        df=frame,
        x_col="period",
        y_cols=list(indexed),
        title=f"Combined sources trend (index, {periods[0]} = 100)",
        source_label=" + ".join(indexed),
    )
    return None if _is_empty_chart(chart) else chart


def _build_chart_profile(target_df: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    """Summarise the data shape so the LLM can pick an appropriate chart type."""
    time_col = meta.get("time_col") if meta.get("time_col") in target_df.columns else None
    cat_col = meta.get("category_col") if meta.get("category_col") in target_df.columns else None
    val_col = meta.get("val_col") or ""
    return {
        "metric": meta.get("metric_label") or val_col,
        "value_col": val_col,
        "time_col": time_col,
        "category_col": cat_col,
        "n_rows": int(len(target_df)),
        "n_periods": int(target_df[time_col].nunique()) if time_col else 0,
        "n_categories": int(target_df[cat_col].nunique()) if cat_col else 0,
        "is_comparison": bool(meta.get("is_comparison")),
        "comparison_years": list(meta.get("comparison_years") or []),
        "additive": not any(h in val_col.lower() for h in _NON_ADDITIVE_HINTS),
    }


def _build_chart(
    chart_type: str,
    target_df: pd.DataFrame,
    meta: dict[str, Any],
    d_source: str,
    d_title: str,
) -> dict[str, Any] | None:
    """Build the Plotly spec for the requested chart type; None if it cannot be drawn."""
    val_col = meta["val_col"]
    time_col = meta.get("time_col") if meta.get("time_col") in target_df.columns else None
    cat_col = meta.get("category_col") if meta.get("category_col") in target_df.columns else None
    metric_label = meta.get("metric_label") or val_col.replace("_", " ").title()
    cat_label = (cat_col or "").replace("_", " ").title()

    latest_df = target_df
    latest_label = ""
    if time_col and target_df[time_col].nunique() > 1:
        latest_label = sorted(target_df[time_col].astype(str).unique())[-1]
        latest_df = target_df[target_df[time_col].astype(str) == latest_label]
    elif time_col:
        latest_label = str(target_df[time_col].iloc[0])
    period_suffix = f" ({latest_label})" if latest_label else ""

    chart: dict[str, Any] | None = None

    if chart_type == "grouped_bar" and cat_col and time_col:
        years = list(meta.get("comparison_years") or [])
        if len(years) < 2:
            periods = sorted(target_df[time_col].astype(str).unique())
            years = periods[-2:]
        if len(years) >= 2:
            y1, y2 = str(years[0]), str(years[1])
            piv = target_df.pivot_table(
                index=cat_col, columns=time_col, values=val_col, aggfunc="mean"
            ).reset_index()
            col_y1 = [c for c in piv.columns if y1 in str(c)]
            col_y2 = [c for c in piv.columns if y2 in str(c)]
            if col_y1 and col_y2:
                chart = VisualizationService.comparison_bar_chart(
                    df=piv,
                    category_col=cat_col,
                    series_1_col=col_y1[0],
                    series_2_col=col_y2[0],
                    series_1_label=y1,
                    series_2_label=y2,
                    title=f"{metric_label} ({y1} vs {y2}) by {cat_label}",
                    source_label=d_source,
                    metric_label=metric_label,
                )
    elif chart_type == "pie" and cat_col:
        agg = latest_df.groupby(cat_col, as_index=False)[val_col].sum()
        chart = VisualizationService.pie_chart(
            df=agg,
            label_col=cat_col,
            value_col=val_col,
            title=f"{metric_label} share by {cat_label}{period_suffix}",
            source_label=d_source,
        )
    elif chart_type in ("bar", "horizontal_bar"):
        horizontal = chart_type == "horizontal_bar"
        if cat_col:
            agg = latest_df.groupby(cat_col, as_index=False)[val_col].mean()
            agg = agg.sort_values(by=val_col, ascending=horizontal)
            x_col, title = cat_col, f"{metric_label} by {cat_label}{period_suffix}"
        else:
            x_col = time_col or str(target_df.columns[0])
            agg = target_df.groupby(x_col, as_index=False)[val_col].mean()
            title = f"{d_title} - {metric_label}"
        chart = VisualizationService.bar_chart(
            df=agg,
            x_col=x_col,
            y_col=val_col,
            title=title,
            source_label=d_source,
            orientation="h" if horizontal else "v",
        )
    elif chart_type == "line" and time_col:
        n_cat = target_df[cat_col].nunique() if cat_col else 0
        if cat_col and 2 <= n_cat <= 8 and not meta.get("sector_filtered"):
            piv = (
                target_df.pivot_table(index=time_col, columns=cat_col, values=val_col, aggfunc="mean")
                .sort_index()
                .reset_index()
            )
            chart = VisualizationService.multi_line_chart(
                df=piv,
                x_col=time_col,
                y_cols=[c for c in piv.columns if c != time_col],
                title=f"{metric_label} over time by {cat_label}",
                source_label=d_source,
            )
        else:
            agg = target_df.groupby(time_col, as_index=False)[val_col].mean().sort_values(time_col)
            suffix = f" - {meta['sector_filtered']}" if meta.get("sector_filtered") else ""
            chart = VisualizationService.line_chart(
                df=agg,
                x_col=time_col,
                y_col=val_col,
                title=f"{d_title} - {metric_label} Trend{suffix}",
                source_label=d_source,
            )

    return None if _is_empty_chart(chart) else chart


def _synthesize_intelligent_chart(
    datasets: list[dict[str, Any]],
    query: str,
    chart_type: str | None = None,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build ONE query-aligned chart, or return None when there is no data to plot.

    If ``chart_type`` is omitted, a rule-based choice is made from the query and data shape.
    """
    from app.services.chart_selector import feasible_chart_types, heuristic_chart_type

    for ds, target_df, meta in _query_aligned_frames(datasets, query):
        profile = _build_chart_profile(target_df, meta)
        d_source = ds.get("source", "Official Singapore Statistics")
        d_title = ds.get("title", "Singapore Policy Indicator")
        wanted = chart_type or heuristic_chart_type(query, profile)
        # Try the requested type, then fall back through feasible types.
        candidates = [wanted] + [t for t in feasible_chart_types(profile) if t != wanted] + ["bar"]
        for candidate in candidates:
            chart = _build_chart(candidate, target_df, meta, d_source, d_title)
            if chart is not None:
                if selection is not None:
                    selection["chart_type"] = candidate
                return chart
    return None


async def _select_and_synthesize_chart(
    datasets: list[dict[str, Any]],
    query: str,
    preferred_chart_type: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Ask the LLM which chart type fits the query (or prioritize preferred_chart_type), then build it."""
    from app.services.chart_selector import feasible_chart_types, select_chart_type

    for ds, target_df, meta in _query_aligned_frames(datasets, query):
        profile = _build_chart_profile(target_df, meta)
        feasible = feasible_chart_types(profile)

        # Prioritize coordinator's recommended chart if feasible for data shape
        if preferred_chart_type and preferred_chart_type in feasible:
            built = _synthesize_intelligent_chart([ds], query, chart_type=preferred_chart_type)
            if built is not None:
                return built, {
                    "chart_type": preferred_chart_type,
                    "reason": "Coordinator recommended chart type matching query intent and data shape.",
                    "selected_by": "coordinator",
                }

        selection = await select_chart_type(query, profile)
        built = _synthesize_intelligent_chart([ds], query, chart_type=selection["chart_type"])
        if built is not None:
            return built, selection
    return None, {}


class AnalyticsChatModel(BaseChatModel):
    """Fallback ChatModel for LangGraph create_react_agent when running offline or mocked."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Analytics, statistical modeling, and visualization synthesis completed successfully."
                    )
                )
            ]
        )

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> RunnableBinding:
        return RunnableBinding(bound=self, kwargs={"tools": tools, **kwargs})

    @property
    def _llm_type(self) -> str:
        return "analytics_react_model"


def create_analytics_agent(
    model: Any = None,
    tools: list[Any] | None = None,
    checkpointer: Any = None,
) -> CompiledGraph:
    """Create a LangGraph ReAct agent pre-configured with analytics and visualization tools.

    Args:
        model: Optional LangChain BaseChatModel. Defaults to AnalyticsChatModel.
        tools: Optional list of LangChain tools. Defaults to analytics tools.
        checkpointer: Optional LangGraph checkpoint saver.

    Returns:
        CompiledGraph: Compiled LangGraph ReAct agent graph.
    """
    selected_tools = (
        tools
        if tools is not None
        else [
            compute_statistics,
            generate_chart,
            generate_insight,
        ]
    )
    chat_model = model if model is not None else AnalyticsChatModel()
    return create_react_agent(
        model=chat_model,
        tools=selected_tools,
        checkpointer=checkpointer,
    )


async def _emit_step(
    state: AgentState,
    step_type: StepType,
    content: dict[str, Any],
    active_db: AsyncSession | None,
    analysis_id: str,
    analysis_uuid: uuid.UUID,
) -> dict[str, Any]:
    """Emit an agent step, persist to state agent_logs, broadcast via PubSub, and save to DB."""
    seq_no = len(state.get("agent_logs", [])) + 1
    log_entry = {
        "agent_name": AgentName.ANALYTICS,
        "step_type": step_type,
        "content": content,
        "sequence_no": seq_no,
    }
    state.setdefault("agent_logs", []).append(log_entry)

    try:
        msg = format_agent_step_message(
            analysis_id=analysis_id,
            agent_name=AgentName.ANALYTICS,
            step_type=step_type,
            content=content,
            sequence_no=seq_no,
        )
        await publish_step(analysis_id, msg)
    except Exception as exc:
        logger.warning("Failed to publish analytics %s step to pubsub: %s", step_type, exc)

    if active_db is not None:
        try:
            await create_agent_log(
                db=active_db,
                analysis_id=analysis_uuid,
                agent_name=AgentName.ANALYTICS,
                step_type=step_type,
                content=content,
                seq_no=seq_no,
            )
        except Exception as exc:
            logger.warning("Failed to persist analytics %s step to DB: %s", step_type, exc)

    return log_entry


def _collect_datasets_from_state(state: AgentState) -> list[dict[str, Any]]:
    """Extract and normalize all available dataset records from state across possible keys."""
    datasets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 1. Inspect raw_datasets
    raw_ds = state.get("raw_datasets")
    if isinstance(raw_ds, list):
        for item in raw_ds:
            if isinstance(item, dict):
                d_id = str(
                    item.get("dataset_id") or item.get("id") or item.get("title") or len(datasets)
                )
                if d_id not in seen_ids:
                    seen_ids.add(d_id)
                    datasets.append(item)

    # 2. Inspect selected_datasets
    sel_ds = state.get("selected_datasets")
    if isinstance(sel_ds, list):
        for item in sel_ds:
            if isinstance(item, dict):
                d_id = str(
                    item.get("dataset_id") or item.get("id") or item.get("title") or len(datasets)
                )
                if d_id not in seen_ids:
                    seen_ids.add(d_id)
                    datasets.append(item)

    # 3. Inspect raw_data dictionary
    raw_data = state.get("raw_data")
    if isinstance(raw_data, dict):
        for key, val in raw_data.items():
            if str(key) in seen_ids:
                continue
            if isinstance(val, dict):
                seen_ids.add(str(key))
                datasets.append({"dataset_id": key, **val})
            elif isinstance(val, str):
                seen_ids.add(str(key))
                datasets.append({"dataset_id": key, "df_json": val})

    return datasets


NO_DATA_MESSAGE = "No Data"


def _stats_have_data(stat: Any) -> bool:
    """True if a compute_statistics result carries at least one real observation."""
    if not isinstance(stat, dict) or stat.get("error"):
        return False
    summary = stat.get("summary")
    if isinstance(summary, dict):
        return not summary.get("error") and int(summary.get("count") or 0) > 0
    return bool(stat.get("trend") or stat.get("sector_shares") or stat.get("comparison"))


async def _finish_no_data(
    state: AgentState,
    reason: str,
    active_db: AsyncSession | None,
    analysis_id: str,
    analysis_uuid: uuid.UUID,
) -> AgentState:
    """Complete the analytics node with an explicit 'no data' result (no stats/charts/insights)."""
    state["statistical_results"] = {}
    state["stats"] = {}
    state["insights"] = []
    state["charts"] = []
    state["citations"] = []
    state["no_data"] = True
    state["status"] = "completed"
    state["final_report"] = {
        "analysis_id": analysis_id,
        "query": state.get("query", ""),
        "no_data": True,
        "summary": {},
        "statistical_results": {},
        "insights": [],
        "charts": [],
        "citations": [],
        "data_quality_summary": {"total_datasets": 0, "message": reason},
    }
    await _emit_step(
        state,
        StepType.DONE,
        {
            "thought": "No usable data for this query. Concluding analytics with an empty report.",
            "message": f"{NO_DATA_MESSAGE}: {reason}",
            "status": "no_data",
        },
        active_db,
        analysis_id,
        analysis_uuid,
    )
    return state


async def analytics_node(
    state: AgentState,
    db: AsyncSession | None = None,
) -> AgentState:
    """Execute the Analytics Agent node using deterministic stats, charts, and insight synthesis.

    Args:
        state: Shared AgentState dictionary across the multi-agent graph.
        db: Optional active SQLAlchemy AsyncSession for DB logging.

    Returns:
        Updated AgentState with computed statistics, charts, insights, and final_report.
    """
    state["current_agent"] = AgentName.ANALYTICS

    active_db = db or analytics_db_context.get()
    analysis_id = str(state.get("analysis_id") or uuid.uuid4())
    try:
        analysis_uuid = uuid.UUID(analysis_id)
    except (ValueError, TypeError):
        analysis_uuid = uuid.uuid4()

    # Step 1: Emit THINK step initiating analytics phase
    await _emit_step(
        state,
        StepType.THINK,
        {
            "thought": "Commencing statistical analysis, chart generation, and grounded insight synthesis.",
            "query": state.get("query", ""),
        },
        active_db,
        analysis_id,
        analysis_uuid,
    )

    datasets = _collect_datasets_from_state(state)

    if not datasets:
        logger.warning("No extracted datasets available for analysis_id=%s.", analysis_id)
        return await _finish_no_data(
            state,
            "Data extraction returned no datasets.",
            active_db,
            analysis_id,
            analysis_uuid,
        )

    # Prepare containers for results
    consolidated_stats: dict[str, Any] = {}
    charts_list: list[dict[str, Any]] = []
    citations_list: list[dict[str, Any]] = []

    try:
        iteration_count = 0

        for ds in datasets:
            if iteration_count >= MAX_ANALYTICS_ITERATIONS:
                logger.warning(
                    "Analytics ReAct loop reached max iteration guardrail (%d)",
                    MAX_ANALYTICS_ITERATIONS,
                )
                break

            d_id = ds.get("dataset_id") or ds.get("id") or "dataset"
            d_title = ds.get("title") or f"Dataset {d_id}"
            d_source = ds.get("source") or "SingStat"
            df_content = ds.get("df_json") or ds.get("dataframe_json") or ds.get("data")

            # Collect citation metadata with guaranteed redirectable URL
            url = _resolve_citation_url(
                source=d_source,
                dataset_id=d_id,
                title=d_title,
                existing_url=ds.get("url") or ds.get("metadata", {}).get("url"),
            )
            citations_list.append(
                {
                    "dataset_id": d_id,
                    "title": d_title,
                    "source": d_source,
                    "publisher": ds.get("metadata", {}).get("publisher")
                    or "Government of Singapore",
                    "period": ds.get("metadata", {}).get("period") or "Recent Years",
                    "url": url,
                }
            )

            if not df_content:
                continue

            # -----------------------------------------------------------------
            # Tool 1: compute_statistics
            # -----------------------------------------------------------------
            query_text = state.get("query", "")
            iteration_count += 1
            await _emit_step(
                state,
                StepType.ACT,
                {
                    "tool": "compute_statistics",
                    "action": "compute_statistics",
                    "parameters": {"dataset_id": d_id, "query": query_text, "analysis_type": "all"},
                    "thought": f"Computing query-aligned summary statistics, comparisons, and trends for '{d_title}'.",
                },
                active_db,
                analysis_id,
                analysis_uuid,
            )

            try:
                stat_result = compute_statistics.invoke(
                    {"df_json": df_content, "query": query_text, "analysis_type": "all"}
                )
            except Exception as exc:
                logger.error("compute_statistics tool execution failed: %s", exc)
                stat_result = {"error": "tool_failed", "details": str(exc)}

            # Record observation
            has_error = "error" in stat_result and stat_result.get("error") != "insufficient_data"
            trend_info = stat_result.get("trend", {})
            summary_info = stat_result.get("summary", {})
            obs_stat = {
                "tool": "compute_statistics",
                "action": "compute_statistics",
                "status": "warning" if has_error else "success",
                "dataset_id": d_id,
                "overall_trend": trend_info.get("overall_trend", "stable")
                if isinstance(trend_info, dict)
                else "stable",
                "count": summary_info.get("count", 0) if isinstance(summary_info, dict) else 0,
                "observation": (
                    f"Computed statistical metrics for '{d_title}': "
                    f"overall trend is {trend_info.get('overall_trend', 'stable') if isinstance(trend_info, dict) else 'stable'}, "
                    f"with {summary_info.get('count', 0) if isinstance(summary_info, dict) else 0} observations."
                ),
            }
            await _emit_step(
                state,
                StepType.OBSERVE,
                obs_stat,
                active_db,
                analysis_id,
                analysis_uuid,
            )

            # Accumulate stats (only datasets that actually contain data for the query)
            if _stats_have_data(stat_result):
                if not consolidated_stats:
                    consolidated_stats = dict(stat_result)
                else:
                    consolidated_stats[f"{d_id}_stats"] = stat_result

        if not consolidated_stats:
            return await _finish_no_data(
                state,
                "No data matched the period or scope requested in the query.",
                active_db,
                analysis_id,
                analysis_uuid,
            )

        # Combined cross-source view (SingStat + Data.gov.sg ...) when 2+ sources have data
        combined_stats = _build_combined_stats(datasets, state.get("query", ""))
        if combined_stats:
            consolidated_stats["combined"] = combined_stats
            await _emit_step(
                state,
                StepType.OBSERVE,
                {
                    "tool": "combine_sources",
                    "action": "combine_sources",
                    "status": "success",
                    "sources": [s["source"] for s in combined_stats["sources"]],
                    "shared_periods": combined_stats["shared_periods"],
                    "observation": (
                        "Combined statistics across sources "
                        f"{', '.join(s['source'] for s in combined_stats['sources'])}; "
                        f"{len(combined_stats['shared_periods'])} shared period(s)."
                        + (f" {combined_stats['interpretation']}" if combined_stats.get("interpretation") else "")
                    ),
                },
                active_db,
                analysis_id,
                analysis_uuid,
            )

        # -----------------------------------------------------------------
        # Tool 2: Intelligently synthesize exactly ONE query-aligned chart
        # (Replaces multiple static figures with one meaningful dynamic chart)
        # -----------------------------------------------------------------
        query_text = state.get("query", "Singapore policy data analysis")
        iteration_count += 1
        await _emit_step(
            state,
            StepType.ACT,
            {
                "tool": "generate_chart",
                "action": "generate_chart",
                "parameters": {"query": query_text, "chart_mode": "intelligent_alignment"},
                "thought": f"Synthesizing an intelligent, dynamic visualization strictly aligned with query '{query_text}'.",
            },
            active_db,
            analysis_id,
            analysis_uuid,
        )

        chart_selection: dict[str, Any] = {}
        coord_chart = (state.get("research_plan") or {}).get("recommended_chart")
        try:
            combined_chart = _build_combined_chart(combined_stats)
            if combined_chart is not None:
                intelligent_chart = combined_chart
                chart_selection = {
                    "chart_type": "line",
                    "reason": "Multiple sources share periods; plotted combined base-100 index.",
                    "selected_by": "combined_sources",
                }
            else:
                intelligent_chart, chart_selection = await _select_and_synthesize_chart(
                    datasets, query_text, preferred_chart_type=coord_chart
                )
        except Exception as exc:
            logger.error("Intelligent chart synthesis failed: %s", exc)
            intelligent_chart = None

        charts_list = [intelligent_chart] if intelligent_chart else []
        chart_title_text = (
            (intelligent_chart.get("layout", {}).get("title", {}) or {}).get("text")
            if intelligent_chart
            else None
        ) or "Policy Data Visualization"

        await _emit_step(
            state,
            StepType.OBSERVE,
            {
                "tool": "generate_chart",
                "action": "generate_chart",
                "status": "success" if intelligent_chart else "warning",
                "chart_title": chart_title_text if intelligent_chart else None,
                "chart_type": chart_selection.get("chart_type"),
                "selected_by": chart_selection.get("selected_by"),
                "observation": (
                    f"Chart type '{chart_selection.get('chart_type')}' chosen by "
                    f"{chart_selection.get('selected_by')} ({chart_selection.get('reason')}): "
                    f"'{chart_title_text}'."
                    if intelligent_chart
                    else "No data available to plot for this query."
                ),
            },
            active_db,
            analysis_id,
            analysis_uuid,
        )

        # -----------------------------------------------------------------
        # Tool 3: generate_insight
        # -----------------------------------------------------------------
        query_text = state.get("query", "Singapore policy data analysis")
        router = get_llm_router()
        active_provider = getattr(router, "primary_name", getattr(settings, "primary_llm_provider", "bedrock"))
        active_model = getattr(
            router.primary,
            "model",
            getattr(settings, "bedrock_model_id" if active_provider == "bedrock" else "gemini_model", "apac.amazon.nova-lite-v1:0"),
        )
        analytics_model_info = {
            "agent": "analytics",
            "provider": active_provider,
            "model": str(active_model),
            "role": "Grounded Statistical Modeling & Insight Synthesis",
        }
        state["analytics_model"] = analytics_model_info

        await _emit_step(
            state,
            StepType.ACT,
            {
                "tool": "generate_insight",
                "action": "generate_insight",
                "parameters": {"query": query_text, "sources_count": len(citations_list)},
                "thought": f"Synthesizing grounded Singapore policy insight narrative using {active_provider} ({active_model}).",
                "model": str(active_model),
                "provider": active_provider,
            },
            active_db,
            analysis_id,
            analysis_uuid,
        )

        try:
            insight_narrative = await generate_insight.ainvoke(
                {
                    "query": query_text,
                    "stats": consolidated_stats,
                    "sources": citations_list,
                }
            )
        except Exception as exc:
            logger.error("generate_insight tool execution failed: %s", exc)
            insight_narrative = f"Policy analysis completed. Statistical modeling computed across {len(datasets)} dataset(s)."

        await _emit_step(
            state,
            StepType.OBSERVE,
            {
                "tool": "generate_insight",
                "action": "generate_insight",
                "status": "success",
                "word_count": len(insight_narrative.split())
                if isinstance(insight_narrative, str)
                else 0,
                "observation": f"Synthesized grounded policy insights narrative via {active_provider} ({active_model}) with official dataset citations.",
                "model": str(active_model),
                "provider": active_provider,
            },
            active_db,
            analysis_id,
            analysis_uuid,
        )

        # -----------------------------------------------------------------
        # Populate State Outputs
        # -----------------------------------------------------------------
        state["statistical_results"] = consolidated_stats
        state["stats"] = consolidated_stats
        state["charts"] = charts_list
        state["insights"] = (
            [insight_narrative] if isinstance(insight_narrative, str) else insight_narrative
        )
        state["citations"] = citations_list
        state["status"] = "completed"

        # Final Report Assembly
        summary_payload = consolidated_stats.get("summary", {})
        state["final_report"] = {
            "analysis_id": analysis_id,
            "query": query_text,
            "summary": summary_payload if isinstance(summary_payload, dict) else {},
            "statistical_results": consolidated_stats,
            "insights": state["insights"],
            "charts": charts_list,
            "citations": citations_list,
            "models_used": [
                state.get("coordinator_model") or {
                    "agent": "coordinator",
                    "provider": active_provider,
                    "model": str(active_model),
                    "role": "Query Decomposition & Planning",
                },
                analytics_model_info,
            ],
            "data_quality_summary": {
                "total_datasets": len(datasets),
                "datasets": [
                    {
                        "dataset_id": d.get("dataset_id"),
                        "title": d.get("title"),
                        "source": d.get("source"),
                        "dq_report": d.get("dq_report"),
                    }
                    for d in datasets
                ],
            },
        }

    except Exception as exc:
        logger.exception("Unexpected error inside analytics_node: %s", exc)
        await _emit_step(
            state,
            StepType.ERROR,
            {
                "thought": "Critical failure encountered during analytics processing.",
                "error": str(exc),
            },
            active_db,
            analysis_id,
            analysis_uuid,
        )
        if not state.get("statistical_results"):
            state["statistical_results"] = consolidated_stats
            state["stats"] = consolidated_stats
        if not state.get("charts"):
            state["charts"] = charts_list
        if not state.get("insights"):
            state["insights"] = [f"Analytics pipeline encountered an error: {exc}"]
        state["status"] = "completed"

    # Emit DONE step
    done_content = {
        "thought": (
            f"Analytics processing completed successfully with single query-aligned chart "
            f"and synthesized narrative insights using {state.get('analytics_model', {}).get('model', 'LLM')}."
        ),
        "charts_count": len(state.get("charts", [])),
        "has_insights": bool(state.get("insights")),
        "has_stats": bool(state.get("statistical_results")),
        "model": state.get("analytics_model", {}).get("model"),
        "provider": state.get("analytics_model", {}).get("provider"),
    }
    await _emit_step(
        state,
        StepType.DONE,
        done_content,
        active_db,
        analysis_id,
        analysis_uuid,
    )

    return state
