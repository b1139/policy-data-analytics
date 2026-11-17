"""Unit tests for Analytics Agent node, analysis tools, Plotly charts, and graph integration."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.analytics import (
    analytics_node,
    create_analytics_agent,
)
from app.agents.graph import build_graph
from app.agents.state import AgentName, StepType, create_initial_state
from app.agents.tools.analysis_tools import (
    compute_statistics,
    generate_chart,
    generate_insight,
)
from app.core.database import Base
from app.data_sources import MockInternalDataSource, data_source_registry
from app.models.agent_log import AgentLog


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def ensure_mock_source_registered() -> None:
    """Ensure MockInternalDataSource is registered."""
    mock_src = MockInternalDataSource()
    data_source_registry.register(mock_src, overwrite=True)


@pytest.fixture
def sample_timeseries_df() -> pd.DataFrame:
    """Provide sample time-series data for employment in Singapore."""
    return pd.DataFrame(
        {
            "year": [2019, 2020, 2021, 2022, 2023, 2024],
            "employment": [120000.0, 118000.0, 122000.0, 126000.0, 130000.0, 134000.0],
            "sector": ["Tech", "Tech", "Tech", "Tech", "Tech", "Tech"],
        }
    )


@pytest.fixture
def sample_sector_df() -> pd.DataFrame:
    """Provide sample sectoral distribution data."""
    return pd.DataFrame(
        {
            "sector": ["Technology", "Finance", "Manufacturing", "Healthcare"],
            "employment": [55000.0, 48000.0, 36000.0, 25000.0],
            "year": [2024, 2024, 2024, 2024],
        }
    )


# ==============================================================================
# 1. Analysis Tools Tests
# ==============================================================================


def test_tool_compute_statistics_all(sample_timeseries_df: pd.DataFrame) -> None:
    """compute_statistics computes trend, summary, and metadata for a DataFrame."""
    df_json = sample_timeseries_df.to_json(orient="split")
    result = compute_statistics.invoke({"df_json": df_json, "analysis_type": "all"})

    assert isinstance(result, dict)
    assert "summary" in result
    assert result["summary"]["count"] == 6
    assert result["summary"]["mean"] > 100000.0
    assert "trend" in result
    assert result["trend"]["overall_trend"] in ["increasing", "stable", "decreasing"]
    assert "yoy_growth" in result["trend"]


def test_tool_compute_statistics_trend(sample_timeseries_df: pd.DataFrame) -> None:
    """compute_statistics computes trend specifically when requested."""
    df_json = sample_timeseries_df.to_json(orient="split")
    result = compute_statistics.invoke({"df_json": df_json, "analysis_type": "trend"})

    assert "trend" in result
    assert result["trend"]["slope"] is not None
    assert result["trend"]["r2"] is not None


def test_tool_compute_statistics_sector_share(sample_sector_df: pd.DataFrame) -> None:
    """compute_statistics computes sector shares for sectoral data."""
    df_json = sample_sector_df.to_json(orient="split")
    result = compute_statistics.invoke({"df_json": df_json, "analysis_type": "sector_share"})

    assert "sector_shares" in result
    shares = result["sector_shares"]["shares"]
    assert "Technology" in shares
    assert round(sum(shares.values())) == 100


def test_tool_compute_statistics_empty() -> None:
    """compute_statistics handles empty or invalid inputs gracefully."""
    result = compute_statistics.invoke({"df_json": "", "analysis_type": "all"})
    assert "error" in result
    assert result["error"] == "empty_dataframe"


def test_tool_generate_chart_line(sample_timeseries_df: pd.DataFrame) -> None:
    """generate_chart produces a valid Plotly line chart specification."""
    df_json = sample_timeseries_df.to_json(orient="split")
    chart_spec = generate_chart.invoke(
        {
            "df_json": df_json,
            "chart_type": "line",
            "title": "Tech Employment Trajectory",
            "source_label": "SingStat",
        }
    )

    assert isinstance(chart_spec, dict)
    assert "data" in chart_spec
    assert "layout" in chart_spec
    assert len(chart_spec["data"]) > 0
    assert chart_spec["data"][0]["type"] == "scatter"
    assert chart_spec["data"][0]["mode"] == "lines+markers"
    assert (
        chart_spec["layout"]["template"]["layout"]["colorway"] is not None
        or "template" in chart_spec["layout"]
    )


def test_tool_generate_chart_bar(sample_sector_df: pd.DataFrame) -> None:
    """generate_chart produces a valid Plotly bar chart specification."""
    df_json = sample_sector_df.to_json(orient="split")
    chart_spec = generate_chart.invoke(
        {
            "df_json": df_json,
            "chart_type": "bar",
            "title": "Sector Employment",
            "source_label": "MOM",
        }
    )

    assert isinstance(chart_spec, dict)
    assert "data" in chart_spec
    assert chart_spec["data"][0]["type"] == "bar"


def test_tool_generate_chart_empty() -> None:
    """generate_chart returns empty_chart indicator when DataFrame has no data."""
    chart_spec = generate_chart.invoke({"df_json": "[]", "chart_type": "line"})
    assert chart_spec.get("type") == "empty_chart"


@pytest.mark.asyncio
async def test_tool_generate_insight(sample_timeseries_df: pd.DataFrame) -> None:
    """generate_insight synthesizes policy narrative using LLM router or template fallback."""
    df_json = sample_timeseries_df.to_json(orient="split")
    stats_data = compute_statistics.invoke({"df_json": df_json, "analysis_type": "all"})

    insight = await generate_insight.ainvoke(
        {
            "query": "How has tech employment changed in Singapore?",
            "stats": stats_data,
            "sources": [{"title": "SingStat Employment", "period": "2019-2024"}],
        }
    )

    assert isinstance(insight, str)
    assert len(insight) > 100
    assert "Singapore" in insight or "policy" in insight.lower()


# ==============================================================================
# 2. Analytics Node Unit Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_analytics_node_with_mock_datasets(
    sample_timeseries_df: pd.DataFrame,
    sample_sector_df: pd.DataFrame,
) -> None:
    """analytics_node processes extracted datasets and populates stats, charts, and insights."""
    state = create_initial_state(
        analysis_id=str(uuid.uuid4()),
        query="Analyze employment trends and sector breakdown in Singapore",
    )
    state["raw_datasets"] = [
        {
            "source": "singstat",
            "dataset_id": "sg_tech_employment",
            "title": "Tech Employment Series",
            "df_json": sample_timeseries_df.to_json(orient="split"),
            "metadata": {"publisher": "SingStat", "period": "2019-2024"},
        },
        {
            "source": "singstat",
            "dataset_id": "sg_sector_shares",
            "title": "Sector Employment Shares",
            "df_json": sample_sector_df.to_json(orient="split"),
            "metadata": {"publisher": "MOM", "period": "2024"},
        },
    ]

    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock) as mock_pub:
        res = await analytics_node(state)

    assert res["current_agent"] == "analytics"
    assert res["status"] == "completed"

    # Verify statistical results and stats alias
    assert "statistical_results" in res and bool(res["statistical_results"])
    assert "stats" in res and bool(res["stats"])

    # Verify charts list has minimum 1 chart with Plotly format
    assert isinstance(res["charts"], list)
    assert len(res["charts"]) >= 1
    first_chart = res["charts"][0]
    assert "data" in first_chart and "layout" in first_chart

    # Verify insights populated
    assert isinstance(res["insights"], list)
    assert len(res["insights"]) >= 1
    assert len(res["insights"][0]) > 50

    # Verify final_report assembled
    assert res["final_report"] is not None
    assert "summary" in res["final_report"]
    assert "insights" in res["final_report"]
    assert "charts" in res["final_report"]
    assert "data_quality_summary" in res["final_report"]

    # Verify ACT and OBSERVE steps in agent_logs
    step_types = [log["step_type"] for log in res["agent_logs"]]
    assert StepType.THINK in step_types
    assert StepType.ACT in step_types
    assert StepType.OBSERVE in step_types
    assert StepType.DONE in step_types

    # Verify publish_step called for steps
    assert mock_pub.call_count >= 4


@pytest.mark.asyncio
async def test_analytics_node_empty_datasets_partial_result() -> None:
    """analytics_node emits partial DONE step when no datasets are available in state."""
    state = create_initial_state(
        analysis_id=str(uuid.uuid4()),
        query="Non-existent data query",
    )
    # Ensure all data stores in state are empty
    state["raw_datasets"] = []
    state["selected_datasets"] = []
    state["raw_data"] = {}

    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock):
        res = await analytics_node(state)

    assert res["current_agent"] == "analytics"
    assert res["status"] == "completed"
    assert res["charts"] == []
    assert res["insights"] == [] and res["no_data"] is True
    # Verify DONE step emitted with no_data status
    step_types = [log["step_type"] for log in res["agent_logs"]]
    assert StepType.DONE in step_types
    done_log = [log for log in res["agent_logs"] if log["step_type"] == StepType.DONE][0]
    assert done_log["content"].get("status") == "no_data"


@pytest.mark.asyncio
async def test_analytics_node_db_persistence(
    async_db: AsyncSession,
    sample_timeseries_df: pd.DataFrame,
) -> None:
    """analytics_node persists all execution steps into AgentLog DB records."""
    analysis_uuid = uuid.uuid4()
    state = create_initial_state(
        analysis_id=str(analysis_uuid),
        query="Assess Singapore GDP trajectory",
    )
    state["raw_datasets"] = [
        {
            "source": "singstat",
            "dataset_id": "sg_gdp",
            "title": "Singapore Real GDP",
            "df_json": sample_timeseries_df.to_json(orient="split"),
            "metadata": {"publisher": "SingStat", "period": "2019-2024"},
        }
    ]

    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock):
        await analytics_node(state, db=async_db)

    # Verify records in database
    result = await async_db.execute(select(AgentLog).where(AgentLog.analysis_id == analysis_uuid))
    logs = result.scalars().all()

    assert len(logs) >= 4
    agent_names = {log.agent_name for log in logs}
    assert AgentName.ANALYTICS in agent_names or "analytics" in agent_names

    types = {log.step_type for log in logs}
    assert "THINK" in types
    assert "ACT" in types
    assert "OBSERVE" in types
    assert "DONE" in types


# ==============================================================================
# 3. LangGraph ReAct and Graph Integration
# ==============================================================================


def test_create_analytics_agent() -> None:
    """create_analytics_agent creates a compiled LangGraph ReAct agent graph."""
    agent_graph = create_analytics_agent()
    assert agent_graph is not None
    assert hasattr(agent_graph, "ainvoke")


@pytest.mark.asyncio
async def test_compiled_graph_end_to_end_integration() -> None:
    """build_graph executes full workflow end-to-end through coordinator -> extraction -> analytics."""
    compiled = build_graph()
    analysis_id = str(uuid.uuid4())
    state = create_initial_state(
        analysis_id=analysis_id,
        query="Analyze employment trends in Singapore technology sector",
    )

    with (
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
        patch("app.agents.extraction.publish_step", new_callable=AsyncMock),
        patch("app.agents.analytics.publish_step", new_callable=AsyncMock),
    ):
        final_state = await compiled.ainvoke(state)

    assert final_state["current_agent"] == "analytics"
    assert final_state["status"] == "completed"
    assert final_state["research_plan"] is not None
    assert final_state.get("final_report") is not None
    charts = final_state.get("charts") or final_state["final_report"].get("charts", [])
    assert isinstance(charts, list)
    assert len(charts) >= 1
    assert bool(final_state.get("insights"))


@pytest.mark.asyncio
async def test_combined_sources_statistics_and_chart() -> None:
    """analytics_node combines multi-source series (SingStat + DataGov) into unified statistics and chart."""
    df_singstat = pd.DataFrame(
        {
            "year": [2021, 2022, 2023, 2024],
            "employment_count": [120000.0, 125000.0, 130000.0, 135000.0],
            "sector": ["Tech", "Tech", "Tech", "Tech"],
            "_source": ["singstat"] * 4,
        }
    )
    df_datagov = pd.DataFrame(
        {
            "year": [2021, 2022, 2023, 2024],
            "retrench_count": [4500.0, 4200.0, 3900.0, 3600.0],
            "sector": ["Tech", "Tech", "Tech", "Tech"],
            "_source": ["datagov"] * 4,
        }
    )

    state = create_initial_state(
        analysis_id=str(uuid.uuid4()),
        query="Trends from 2021 to 2024 in tech employment and retrenchment",
    )
    state["selected_datasets"] = [
        {
            "source": "singstat",
            "dataset_id": "M810361",
            "title": "SingStat Resident Employment",
            "df_json": df_singstat.to_json(orient="split"),
        },
        {
            "source": "datagov",
            "dataset_id": "d_000d49cda016c13522d7d5be6a050f59",
            "title": "Data.gov.sg Tech Retrenchment",
            "df_json": df_datagov.to_json(orient="split"),
        },
    ]

    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock):
        result = await analytics_node(state)

    stats = result.get("statistical_results", {})
    assert "combined" in stats
    combined = stats["combined"]
    assert len(combined["sources"]) == 2
    sources = [s["source"] for s in combined["sources"]]
    assert "singstat" in sources and "datagov" in sources
    assert combined["shared_periods"] == ["2021", "2022", "2023", "2024"]
    assert "indexed_series" in combined
    assert "singstat" in combined["indexed_series"]
    assert "datagov" in combined["indexed_series"]
    # Base year 2021 is indexed at 100
    assert combined["indexed_series"]["singstat"]["2021"] == 100.0
    assert combined["indexed_series"]["datagov"]["2021"] == 100.0
    # Correlation computed across 4 periods
    assert combined.get("correlation") is not None
    assert combined["correlation"] < 0  # employment up, retrenchment down -> negative correlation

    # Chart built from combined sources base-100 index
    charts = result.get("charts", [])
    assert len(charts) == 1
    chart = charts[0]
    assert "Combined" in chart.get("layout", {}).get("title", {}).get("text", "")
