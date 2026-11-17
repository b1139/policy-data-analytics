"""Unit tests for Report Generation, Citation Extraction, and AnalysisResult assembly (Story S23)."""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crud.analysis import create_analysis, get_analysis, update_analysis_status
from app.models import Base
from app.schemas import AnalysisResult, AnalysisStatus, ChartSpec, Citation
from app.schemas.analytics import StatsResult, SummaryResult, TrendResult
from app.services import ReportBuilder


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session for DB persistence tests."""
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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def sample_datasets() -> list[dict]:
    """Sample raw datasets with metadata for citation extraction."""
    return [
        {
            "dataset_id": "MOM-MR-01",
            "title": "Singapore Labour Market Report 2023",
            "source": "Ministry of Manpower",
            "url": "https://stats.mom.gov.sg/Pages/Labour-Market-Report-2023.aspx",
            "accessed": "2024-01-15T08:30:00+00:00",
            "metadata": {
                "publisher": "Ministry of Manpower",
                "period": "2019-2023",
            },
        },
        {
            "id": "SINGSTAT-CPI-02",
            "name": "Consumer Price Index (2019=100)",
            "publisher": "Department of Statistics Singapore",
            "source_url": "https://tablebuilder.singstat.gov.sg/table/TS/M212881",
            "metadata": {
                "source": "SingStat",
                "frequency": "Monthly",
            },
        },
    ]


@pytest.fixture
def sample_stats_result() -> StatsResult:
    """Sample populated StatsResult instance."""
    return StatsResult(
        trend=TrendResult(
            slope=2.35,
            intercept=95.0,
            r2=0.91,
            p_value=0.005,
            overall_trend="increasing",
            yoy_growth={"2020": 2.1, "2021": 3.4, "2022": 5.2, "2023": 2.8},
        ),
        summary=SummaryResult(
            mean=105.2,
            median=104.5,
            std=4.8,
            min=98.0,
            max=112.5,
            count=12,
            earliest_value=98.0,
            latest_value=112.5,
        ),
    )


def test_report_builder_full_build(sample_stats_result: StatsResult, sample_datasets: list[dict]):
    """Test ReportBuilder.build with comprehensive valid inputs."""
    insights_text = (
        "Singapore's consumer price index and labour indicators demonstrated robust structural expansion "
        "over the analyzed 2019-2023 evaluation timeframe. The overall trend registered a statistically "
        "significant increasing trajectory with an annualized regression slope of +2.35 (R² = 0.91). "
        "Policy implications suggest maintaining targeted social support subsidies while monitoring core inflationary pressures."
    )

    charts_input = [
        {
            "type": "line",
            "title": "CPI Historical Trajectory",
            "spec": {
                "data": [{"x": [2019, 2020, 2021, 2022, 2023], "y": [98, 100, 103, 108, 112]}],
                "layout": {"title": {"text": "CPI Historical Trajectory"}},
            },
        },
        {
            "type": "bar",
            "title": "Sector Inflation Contribution",
            "spec": {
                "data": [{"x": ["Food", "Housing", "Transport"], "y": [3.2, 4.5, 2.8]}],
                "layout": {"title": {"text": "Sector Inflation Contribution"}},
            },
        },
    ]

    report = ReportBuilder.build(
        insights=insights_text,
        charts=charts_input,
        stats=sample_stats_result,
        datasets=sample_datasets,
    )

    assert isinstance(report, AnalysisResult)
    assert report.insights == insights_text
    assert len(report.charts) == 2
    assert report.charts[0].type == "line"
    assert report.charts[0].title == "CPI Historical Trajectory"
    assert report.charts[1].type == "bar"

    # Verify citations extraction
    assert len(report.citations) == 2
    c1, c2 = report.citations
    assert c1.dataset_id == "MOM-MR-01"
    assert c1.source == "Ministry of Manpower"
    assert c1.title == "Singapore Labour Market Report 2023"
    assert c1.url == "https://stats.mom.gov.sg/Pages/Labour-Market-Report-2023.aspx"
    assert isinstance(c1.accessed, datetime)

    assert c2.dataset_id == "SINGSTAT-CPI-02"
    assert c2.source == "Department of Statistics Singapore"
    assert c2.url == "https://tablebuilder.singstat.gov.sg/table/TS/M212881"

    # Verify stats_summary extraction
    summary = report.stats_summary
    assert summary["trend_direction"] == "increasing"
    assert summary["peak_year"] == 2022  # highest YoY growth (5.2 in 2022)
    assert summary["overall_change_pct"] == round(((112.5 - 98.0) / 98.0) * 100.0, 2)  # 14.8
    assert summary["data_points_count"] == 12

    # Verify truncated_preview
    assert report.truncated_preview == insights_text[:200]
    assert len(report.truncated_preview) <= 200

    # Verify generated_at is recent
    now = datetime.now(UTC)
    assert abs((now - report.generated_at).total_seconds()) < 5.0


def test_citation_extraction_fallback_when_empty():
    """Test that ReportBuilder includes a placeholder citation when no datasets are provided."""
    report = ReportBuilder.build(
        insights="Brief analysis output with no datasets extracted.",
        charts=[],
        stats={},
        datasets=[],
    )

    assert len(report.citations) == 1
    placeholder = report.citations[0]
    assert placeholder.source == "Data not available"
    assert placeholder.title == "Official Singapore Statistics"
    assert placeholder.url is None
    assert placeholder.dataset_id == "unknown"
    assert isinstance(placeholder.accessed, datetime)


def test_citation_extraction_deduplication():
    """Test that identical datasets are deduplicated in citations."""
    duplicate_datasets = [
        {
            "dataset_id": "SINGSTAT-001",
            "title": "Resident Employment Statistics",
            "source": "SingStat",
            "url": "https://singstat.gov.sg",
        },
        {
            "dataset_id": "SINGSTAT-001",
            "title": "Resident Employment Statistics",
            "source": "SingStat",
            "url": "https://singstat.gov.sg",
        },
    ]

    report = ReportBuilder.build(
        insights="Insights here",
        charts=[],
        stats={},
        datasets=duplicate_datasets,
    )

    assert len(report.citations) == 1
    assert report.citations[0].dataset_id == "SINGSTAT-001"


def test_citation_metadata_nested_extraction():
    """Test citation extraction when attributes are nested inside the metadata dictionary."""
    nested_dataset = [
        {
            "metadata": {
                "dataset_id": "HDB-RESALE-01",
                "name": "HDB Resale Price Index",
                "publisher": "Housing & Development Board",
                "url": "https://data.gov.sg/hdb-resale",
                "retrieved_at": "2024-02-01T12:00:00+00:00",
            }
        }
    ]

    report = ReportBuilder.build(
        insights="HDB resale analysis",
        charts=[],
        stats={},
        datasets=nested_dataset,
    )

    assert len(report.citations) == 1
    citation = report.citations[0]
    assert citation.dataset_id == "HDB-RESALE-01"
    assert citation.title == "HDB Resale Price Index"
    assert citation.source == "Housing & Development Board"
    assert citation.url == "https://data.gov.sg/hdb-resale"


def test_stats_summary_from_dict():
    """Test stats_summary extraction when stats is a plain dictionary."""
    raw_stats = {
        "trend_direction": "decreasing",
        "peak_year": 2021,
        "overall_change_pct": -8.45,
        "data_points_count": 24,
    }

    report = ReportBuilder.build(
        insights="Economic indicator declining.",
        charts=[],
        stats=raw_stats,
        datasets=[],
    )

    assert report.stats_summary["trend_direction"] == "decreasing"
    assert report.stats_summary["peak_year"] == 2021
    assert report.stats_summary["overall_change_pct"] == -8.45
    assert report.stats_summary["data_points_count"] == 24


def test_stats_summary_nested_dict_extraction():
    """Test stats_summary extraction from a dictionary containing nested 'trend' and 'summary' keys."""
    nested_stats = {
        "trend": {
            "slope": -1.2,
            "overall_trend": "decreasing",
            "yoy_growth": {"2020": 4.5, "2021": 6.8, "2022": -2.1},
        },
        "summary": {
            "count": 15,
            "earliest_value": 100.0,
            "latest_value": 85.0,
        },
    }

    report = ReportBuilder.build(
        insights="Analysis with nested stats dictionary.",
        charts=[],
        stats=nested_stats,
        datasets=[],
    )

    summary = report.stats_summary
    assert summary["trend_direction"] == "decreasing"
    assert summary["peak_year"] == 2021  # Max YoY growth was 6.8 in 2021
    assert summary["overall_change_pct"] == -15.0  # (85 - 100) / 100 * 100
    assert summary["data_points_count"] == 15


def test_stats_summary_defaults_on_empty_stats():
    """Test that default values are supplied when stats is empty or None."""
    report = ReportBuilder.build(
        insights="Empty stats test",
        charts=[],
        stats=None,
        datasets=[],
    )

    summary = report.stats_summary
    assert summary["trend_direction"] == "stable"
    assert summary["peak_year"] is None
    assert summary["overall_change_pct"] == 0.0
    assert summary["data_points_count"] == 0


def test_truncated_preview_bounds():
    """Test that truncated_preview is correctly populated and bounded to <= 200 chars."""
    # Long insights (> 200 chars)
    long_insights = "A" * 350
    report_long = ReportBuilder.build(
        insights=long_insights,
        charts=[],
        stats={},
        datasets=[],
    )
    assert len(report_long.truncated_preview) == 200
    assert report_long.truncated_preview == "A" * 200

    # Short insights (< 200 chars)
    short_insights = "Singapore GDP growth stabilized at 3.1% in 2024."
    report_short = ReportBuilder.build(
        insights=short_insights,
        charts=[],
        stats={},
        datasets=[],
    )
    assert report_short.truncated_preview == short_insights
    assert len(report_short.truncated_preview) == len(short_insights)

    # Empty insights
    report_empty = ReportBuilder.build(
        insights="",
        charts=[],
        stats={},
        datasets=[],
    )
    assert report_empty.truncated_preview == ""


def test_insights_passed_as_list():
    """Test that a list of insight strings is cleanly joined with double newlines."""
    insights_list = [
        "Paragraph 1: Headline trend analysis.",
        "Paragraph 2: Detailed statistical distribution across cohorts.",
        "Paragraph 3: Singapore public policy implications and recommendations.",
    ]

    report = ReportBuilder.build(
        insights=insights_list,
        charts=[],
        stats={},
        datasets=[],
    )

    assert "Paragraph 1: Headline trend analysis." in report.insights
    assert "Paragraph 2: Detailed statistical distribution across cohorts." in report.insights
    assert "\n\n" in report.insights


def test_chart_spec_raw_plotly_figure_normalization():
    """Test that raw Plotly figure dictionaries are normalized into ChartSpec models."""
    raw_plotly = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [2021, 2022, 2023],
                "y": [10, 15, 20],
                "name": "CPI",
            }
        ],
        "layout": {
            "title": {"text": "Consumer Price Index 2021-2023"},
            "xaxis": {"title": "Year"},
            "yaxis": {"title": "Index"},
        },
    }

    report = ReportBuilder.build(
        insights="Raw plotly spec normalization test.",
        charts=[raw_plotly],
        stats={},
        datasets=[],
    )

    assert len(report.charts) == 1
    chart_spec = report.charts[0]
    assert isinstance(chart_spec, ChartSpec)
    assert chart_spec.title == "Consumer Price Index 2021-2023"
    assert chart_spec.type == "scatter"
    assert "data" in chart_spec.spec
    assert "layout" in chart_spec.spec


def test_json_serialization_cleanly(sample_stats_result: StatsResult, sample_datasets: list[dict]):
    """Test that model_dump(mode='json') serializes to valid JSON without datetime errors."""
    report = ReportBuilder.build(
        insights="Serialization test narrative with grounded numbers.",
        charts=[
            {
                "type": "line",
                "title": "Trend",
                "spec": {"data": [], "layout": {}},
            }
        ],
        stats=sample_stats_result,
        datasets=sample_datasets,
    )

    # 1. model_dump(mode="json")
    dumped = report.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert isinstance(dumped["generated_at"], str)
    assert isinstance(dumped["citations"][0]["accessed"], str)

    # 2. json.dumps on dumped dictionary
    json_str = json.dumps(dumped)
    assert isinstance(json_str, str)
    assert len(json_str) > 0

    # 3. Round-trip deserialize into AnalysisResult
    loaded_dict = json.loads(json_str)
    reconstituted = AnalysisResult.model_validate(loaded_dict)
    assert reconstituted.insights == report.insights
    assert len(reconstituted.charts) == len(report.charts)
    assert len(reconstituted.citations) == len(report.citations)
    assert reconstituted.stats_summary == report.stats_summary


@pytest.mark.asyncio
async def test_update_analysis_status_db_persistence(
    async_db: AsyncSession,
    sample_stats_result: StatsResult,
    sample_datasets: list[dict],
):
    """Test persisting assembled AnalysisResult to the analyses.result JSONB column via update_analysis_status."""
    # 1. Create analysis record
    analysis = await create_analysis(
        db=async_db,
        query="What is the 5-year trend in Singapore's consumer price index (CPI)?",
    )
    assert analysis.status == AnalysisStatus.PENDING.value
    assert analysis.result is None

    # 2. Build intelligence report
    report = ReportBuilder.build(
        insights="The 5-year CPI trajectory shows an annualized slope of +2.35.",
        charts=[{"type": "line", "title": "CPI Trend", "spec": {"data": []}}],
        stats=sample_stats_result,
        datasets=sample_datasets,
    )
    report_json = report.model_dump(mode="json")

    # 3. Save report via update_analysis_status
    updated = await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status=AnalysisStatus.DONE,
        result=report_json,
    )

    assert updated is not None
    assert updated.status == AnalysisStatus.DONE.value
    assert updated.result is not None
    assert updated.result["stats_summary"]["trend_direction"] == "increasing"
    assert updated.result["stats_summary"]["peak_year"] == 2022
    assert len(updated.result["citations"]) == 2

    # 4. Fetch analysis afresh from database
    persisted = await get_analysis(async_db, analysis.id)
    assert persisted is not None
    assert persisted.status == AnalysisStatus.DONE.value
    assert persisted.result["truncated_preview"] == report.truncated_preview
    assert (
        persisted.result["stats_summary"]["overall_change_pct"]
        == report.stats_summary["overall_change_pct"]
    )


def test_schema_exports():
    """Verify all report and analysis models are properly exported in schemas and services modules."""
    import app.schemas as schemas
    import app.services as services

    assert hasattr(schemas, "AnalysisResult")
    assert hasattr(schemas, "ChartSpec")
    assert hasattr(schemas, "Citation")
    assert hasattr(services, "ReportBuilder")
    assert schemas.Citation is Citation
    assert schemas.ChartSpec is ChartSpec
    assert schemas.AnalysisResult is AnalysisResult
