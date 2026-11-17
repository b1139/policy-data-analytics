"""Unit tests ensuring analytics, charts, and statistics operate strictly based on the user query.

Validates that:
1. Data may be retrieved in full (e.g. 2019–2026 across all sectors), but Pandas filtering
   restricts computations and visualizations exclusively to the user's inquiry (e.g. 2025 vs 2026).
2. The chart for "compare employment growth 2025 vs 2026" generates a comparative visualization
   covering only 2025 and 2026 with growth metrics (yoy_change_pct), not the entire historical dataset.
3. Summary stats and comparisons in compute_statistics are evaluated only on the query-aligned slice.
4. Citation URLs point to functional, direct Singapore official statistics pages without 404s.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.agents.analytics import (
    _resolve_citation_url,
    _synthesize_intelligent_chart,
    analytics_node,
)
from app.agents.state import create_initial_state
from app.agents.tools.analysis_tools import (
    compute_statistics,
    filter_dataframe_by_query,
)
from app.data_sources.mock_internal import _EMPLOYMENT_BY_SECTOR_DATA


@pytest.fixture
def employment_full_df() -> pd.DataFrame:
    """Provide multi-year full employment dataset (2019–2026) across 11 sectors."""
    return pd.DataFrame(_EMPLOYMENT_BY_SECTOR_DATA)


# ==============================================================================
# 1. Pandas Query-Based DataFrame Filtering Tests
# ==============================================================================


def test_filter_dataframe_by_query_comparison_2025_vs_2026(employment_full_df: pd.DataFrame) -> None:
    """filter_dataframe_by_query filters multi-year dataset to strictly 2025 and 2026."""
    query = "compare employment growth 2025 vs 2026"
    filtered_df, meta = filter_dataframe_by_query(employment_full_df, query=query)

    # 1. Row count verification: 11 sectors * 2 years = 22 rows (not 88 rows)
    assert meta["filter_applied"] is True
    assert meta["is_comparison"] is True
    assert meta["comparison_years"] == ("2025", "2026")
    assert meta["target_years"] == ["2025", "2026"]
    assert len(filtered_df) == 22
    assert len(filtered_df) < len(employment_full_df)

    # 2. Strict Year verification: ONLY 2025 and 2026 exist in filtered slice
    years_in_slice = set(filtered_df["year"].astype(str))
    assert years_in_slice == {"2025", "2026"}
    for unrequested_year in ["2019", "2020", "2021", "2022", "2023", "2024"]:
        assert unrequested_year not in years_in_slice

    # 3. Metric Alignment: 'growth' query selects yoy_change_pct over generic headcount
    assert meta["val_col"] == "yoy_change_pct"


def test_filter_dataframe_by_query_headcount_intent(employment_full_df: pd.DataFrame) -> None:
    """filter_dataframe_by_query selects headcount column when query asks for count/level."""
    query = "compare employment headcount in 2024 vs 2025"
    filtered_df, meta = filter_dataframe_by_query(employment_full_df, query=query)

    assert meta["val_col"] == "employment_count"
    years_in_slice = set(filtered_df["year"].astype(str))
    assert years_in_slice == {"2024", "2025"}


def test_filter_dataframe_by_query_single_year(employment_full_df: pd.DataFrame) -> None:
    """filter_dataframe_by_query isolates single year when specified."""
    query = "employment by sector in 2025"
    filtered_df, meta = filter_dataframe_by_query(employment_full_df, query=query)

    assert meta["filter_applied"] is True
    assert set(filtered_df["year"].astype(str)) == {"2025"}
    assert len(filtered_df) == 11


def test_filter_dataframe_by_query_year_range(employment_full_df: pd.DataFrame) -> None:
    """filter_dataframe_by_query filters to date range between two years."""
    query = "employment growth from 2023 to 2025"
    filtered_df, meta = filter_dataframe_by_query(employment_full_df, query=query)

    assert meta["filter_applied"] is True
    assert meta["is_range"] is True
    years_in_slice = set(filtered_df["year"].astype(int))
    assert years_in_slice == {2023, 2024, 2025}


def test_filter_dataframe_by_query_sector_mention(employment_full_df: pd.DataFrame) -> None:
    """filter_dataframe_by_query isolates specified industry sector."""
    query = "compare manufacturing employment growth 2025 vs 2026"
    filtered_df, meta = filter_dataframe_by_query(employment_full_df, query=query)

    assert meta["filter_applied"] is True
    assert meta["val_col"] == "yoy_change_pct"
    assert len(filtered_df) == 2
    assert set(filtered_df["sector"]) == {"Manufacturing"}
    assert set(filtered_df["year"].astype(str)) == {"2025", "2026"}


# ==============================================================================
# 2. Query-Aligned Statistics Computation Tests
# ==============================================================================


def test_compute_statistics_with_query_alignment(employment_full_df: pd.DataFrame) -> None:
    """compute_statistics restricts calculations to 2025 vs 2026 when query provided."""
    df_json = employment_full_df.to_json(orient="split")
    query = "compare employment growth 2025 vs 2026"

    result = compute_statistics.invoke({"df_json": df_json, "query": query, "analysis_type": "all"})

    assert isinstance(result, dict)
    assert "error" not in result

    # 1. Summary stats must be calculated on 22 rows (2025 & 2026), NOT 88 rows
    assert "summary" in result
    assert result["summary"]["count"] == 22

    # 2. Metadata tracks query filter and target years
    assert "metadata" in result
    assert result["metadata"]["filter_applied"] is True
    assert result["metadata"]["target_years"] == ["2025", "2026"]
    assert result["metadata"]["row_count"] == 22
    assert result["metadata"]["original_row_count"] == len(employment_full_df)

    # 3. Direct comparison object populated
    assert "comparison" in result
    comp = result["comparison"]
    assert comp is not None
    assert comp["period_1"] == "2025"
    assert comp["period_2"] == "2026"
    assert comp["metric"] == "yoy_change_pct"
    assert comp["series_1_mean"] is not None
    assert comp["series_2_mean"] is not None
    assert comp["absolute_difference"] is not None
    assert "by_category" in comp
    assert len(comp["by_category"]) == 11


# ==============================================================================
# 3. Intelligent Query-Aligned Chart Synthesis Tests
# ==============================================================================


def test_synthesize_chart_only_contains_user_query_years(employment_full_df: pd.DataFrame) -> None:
    """_synthesize_intelligent_chart generates comparison bar chart containing ONLY 2025 and 2026."""
    query = "compare employment growth 2025 vs 2026"
    datasets = [
        {
            "dataset_id": "employment_by_sector",
            "title": "Employment by Sector",
            "source": "SingStat",
            "df_json": employment_full_df.to_json(orient="split"),
        }
    ]

    chart = _synthesize_intelligent_chart(datasets, query)

    assert isinstance(chart, dict)
    assert "data" in chart and "layout" in chart

    # Chart must have 2 traces: 2025 and 2026
    assert len(chart["data"]) == 2
    series_names = [t["name"] for t in chart["data"]]
    assert "2025" in series_names
    assert "2026" in series_names

    # Check categories (11 sectors)
    assert len(chart["data"][0]["x"]) == 11

    # Verify title reflects specific metric and comparison
    title_text = chart["layout"]["title"]["text"]
    assert "2025 vs 2026" in title_text
    assert "Growth" in title_text or "YoY" in title_text


# ==============================================================================
# 4. Citation URL Directness & Resolution Tests (No 404s)
# ==============================================================================


def test_citation_url_resolution_direct_singstat_and_mom() -> None:
    """_resolve_citation_url produces valid official URLs and fixes broken/404 patterns."""
    # 1. SingStat M-series table code must route to /table/TS/{id}
    url_m = _resolve_citation_url(source="SingStat", dataset_id="M810361")
    assert url_m == "https://tablebuilder.singstat.gov.sg/table/TS/M810361"

    # 2. Existing URL missing /TS/ must be corrected to /TS/
    url_fixed = _resolve_citation_url(
        source="SingStat",
        dataset_id="M810361",
        existing_url="https://tablebuilder.singstat.gov.sg/table/M810361",
    )
    assert url_fixed == "https://tablebuilder.singstat.gov.sg/table/TS/M810361"

    # 3. Employment topic without M-code must route to official SingStat Labour theme
    url_emp = _resolve_citation_url(source="SingStat", dataset_id="employment_by_sector", title="Employment by Sector")
    assert url_emp == "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment"

    # 4. MOM source routes to official MOM Summary table
    url_mom = _resolve_citation_url(source="Ministry of Manpower (MOM)", dataset_id="employment_by_sector")
    assert url_mom == "https://stats.mom.gov.sg/Pages/Employment-Summary-Table.aspx"

    # 5. Data.gov.sg fake hash URL (d_...) must be mapped to valid query search
    url_datagov = _resolve_citation_url(
        source="data.gov.sg",
        dataset_id="ict_workforce_trends",
        title="ICT Workforce",
        existing_url="https://data.gov.sg/datasets/d_e3b8a1c97a5b3a4a6b2c",
    )
    assert "query=" in url_datagov
    assert "d_e3b8a1c9" not in url_datagov


# ==============================================================================
# 5. Full Analytics Node Execution Test with User Query
# ==============================================================================


@pytest.mark.asyncio
async def test_analytics_node_end_to_end_user_query(employment_full_df: pd.DataFrame) -> None:
    """analytics_node executes with query 'compare employment growth 2025 vs 2026' and restricts outputs."""
    query = "compare employment growth 2025 vs 2026"
    state = create_initial_state(
        analysis_id=str(uuid.uuid4()),
        query=query,
    )
    state["raw_datasets"] = [
        {
            "source": "SingStat",
            "dataset_id": "employment_by_sector",
            "title": "Employment by Sector",
            "df_json": employment_full_df.to_json(orient="split"),
            "metadata": {"publisher": "SingStat / MOM", "period": "2019-2026"},
        }
    ]

    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock):
        final_state = await analytics_node(state)

    assert final_state["status"] == "completed"

    # 1. Charts check: exactly 1 chart comparing 2025 vs 2026
    charts = final_state.get("charts", [])
    assert len(charts) == 1
    chart = charts[0]
    series_names = [t.get("name") for t in chart.get("data", [])]
    assert "2025" in series_names
    assert "2026" in series_names

    # 2. Stats check: row count is 22 (strictly 2025 & 2026)
    stats_res = final_state.get("statistical_results", {})
    assert stats_res.get("summary", {}).get("count") == 22
    assert "comparison" in stats_res and stats_res["comparison"] is not None

    # 3. Citations check: valid functional URL
    citations = final_state.get("citations", [])
    assert len(citations) >= 1
    assert citations[0]["url"].startswith("https://")
    assert "/table/employment_by_sector" not in citations[0]["url"]
