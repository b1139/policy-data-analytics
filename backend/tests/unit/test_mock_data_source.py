"""Unit tests for MockInternalDataSource (Story S18).

Verifies the mock internal database connector:
- ABC contract conformance, source_id and display_name
- Catalog coverage of all 5 realistic Singapore datasets (2019–2024)
- Case-insensitive search with single and multiple keywords, filters, and schema
- Fetching normalized DataFrames with UTC timestamps and metadata attrs
- Support for dataset aliases
- Graceful error handling (never raising on invalid dataset IDs)
- Health check and safe health check
- Automatic registration in DataSourceRegistry
"""

from datetime import UTC

import pandas as pd
import pytest

from app.data_sources import (
    MockInternalDataSource,
    auto_register_sources,
    data_source_registry,
)


@pytest.fixture
def mock_source() -> MockInternalDataSource:
    """Fixture providing a fresh MockInternalDataSource instance."""
    return MockInternalDataSource()


# ==============================================================================
# 1. Metadata and ABC Conformance Tests
# ==============================================================================


def test_mock_source_class_attributes(mock_source: MockInternalDataSource) -> None:
    """MockInternalDataSource must define source_id and display_name."""
    assert mock_source.source_id == "mock_internal"
    assert mock_source.display_name == "Mock Internal Database"


def test_mock_source_all_five_datasets_exist(mock_source: MockInternalDataSource) -> None:
    """Mock catalog must contain all 5 required Singapore datasets."""
    expected_ids = {
        "employment_by_sector",
        "ict_workforce_trends",
        "unemployment_rate_quarterly",
        "median_gross_wages",
        "business_registrations",
    }
    assert expected_ids.issubset(set(mock_source._catalog.keys()))


# ==============================================================================
# 2. Search Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_search_all_with_empty_or_wildcard(mock_source: MockInternalDataSource) -> None:
    """Searching with empty string or wildcard '*' must return all 5 datasets."""
    results_empty = await mock_source.search("")
    assert len(results_empty) >= 5

    results_star = await mock_source.search("*")
    assert len(results_star) >= 5


@pytest.mark.asyncio
async def test_search_result_schema(mock_source: MockInternalDataSource) -> None:
    """Every search result item must conform to LLD contract schema."""
    results = await mock_source.search("*")
    for item in results:
        assert isinstance(item, dict)
        assert "id" in item and isinstance(item["id"], str)
        assert "title" in item and isinstance(item["title"], str)
        assert "description" in item and isinstance(item["description"], str)
        assert "url" in item and isinstance(item["url"], str)
        assert "format" in item and isinstance(item["format"], str)
        assert item["url"].startswith("internal://mock_database/")


@pytest.mark.asyncio
async def test_search_single_keyword_matching(mock_source: MockInternalDataSource) -> None:
    """Search matches keywords against title, description, or id case-insensitively."""
    # Employment
    emp_res = await mock_source.search("employment")
    emp_ids = [r["id"] for r in emp_res]
    assert "employment_by_sector" in emp_ids

    # ICT
    ict_res = await mock_source.search("ICT")
    ict_ids = [r["id"] for r in ict_res]
    assert "ict_workforce_trends" in ict_ids

    # Unemployment
    unemp_res = await mock_source.search("unemployment")
    unemp_ids = [r["id"] for r in unemp_res]
    assert "unemployment_rate_quarterly" in unemp_ids

    # Wages
    wages_res = await mock_source.search("WAGES")
    wages_ids = [r["id"] for r in wages_res]
    assert "median_gross_wages" in wages_ids

    # Business Registrations
    biz_res = await mock_source.search("business")
    biz_ids = [r["id"] for r in biz_res]
    assert "business_registrations" in biz_ids


@pytest.mark.asyncio
async def test_search_list_of_keywords(mock_source: MockInternalDataSource) -> None:
    """Search accepts a list of keywords and matches any keyword."""
    res = await mock_source.search(["cleaners", "wages"])
    ids = [r["id"] for r in res]
    assert "median_gross_wages" in ids


@pytest.mark.asyncio
async def test_search_no_match(mock_source: MockInternalDataSource) -> None:
    """Non-matching keywords must return an empty list without error."""
    res = await mock_source.search("extraterrestrial_mining_data_xyz")
    assert res == []


@pytest.mark.asyncio
async def test_search_with_industry_filter(mock_source: MockInternalDataSource) -> None:
    """Search respects optional industry filter."""
    res = await mock_source.search("*", industry="Information & Communications")
    ids = [r["id"] for r in res]
    assert "ict_workforce_trends" in ids
    assert "unemployment_rate_quarterly" not in ids


# ==============================================================================
# 3. Fetch Tests for All 5 Datasets
# ==============================================================================


@pytest.mark.asyncio
async def test_fetch_employment_by_sector(mock_source: MockInternalDataSource) -> None:
    """Verify employment_by_sector dataset schema and realistic figures."""
    df = await mock_source.fetch("employment_by_sector")

    assert not df.empty
    assert len(df) >= 66  # At least 11 sectors * 6 years (2019-2024+)

    expected_cols = {"year", "period_start", "sector", "employment_count", "yoy_change_pct"}
    assert expected_cols.issubset(set(df.columns))

    # Check 11 sectors present
    sectors = set(df["sector"].unique())
    assert len(sectors) == 11
    assert "Manufacturing" in sectors
    assert "Information & Communications" in sectors
    assert "Financial & Insurance Services" in sectors
    assert "Community, Social & Personal Services" in sectors

    # Check years 2019 to 2024 are covered
    years = sorted(df["year"].unique())
    assert {2019, 2020, 2021, 2022, 2023, 2024}.issubset(set(years))

    # Check period_start normalized to UTC timestamp
    assert pd.api.types.is_datetime64_any_dtype(df["period_start"])
    assert df["period_start"].dt.tz == UTC

    # Check metadata attrs
    assert df.attrs["source"] == "mock_internal"
    assert df.attrs["dataset_id"] == "employment_by_sector"
    assert "fetched_at" in df.attrs


@pytest.mark.asyncio
async def test_fetch_ict_workforce_trends(mock_source: MockInternalDataSource) -> None:
    """Verify ict_workforce_trends schema and scale."""
    df = await mock_source.fetch("ict_workforce_trends")

    assert not df.empty
    assert len(df) >= 6  # 2019-2024+

    expected_cols = {
        "year",
        "period_start",
        "ict_headcount",
        "total_workforce",
        "pct_of_workforce",
        "yoy_growth",
    }
    assert expected_cols.issubset(set(df.columns))

    # Tech headcount between 180k and 300k
    assert (df["ict_headcount"] > 180.0).all()
    assert (df["ict_headcount"] < 300.0).all()

    # Total workforce ~3.5M - 3.9M
    assert (df["total_workforce"] > 3500.0).all()
    assert (df["total_workforce"] < 4000.0).all()

    # Tech workforce % between 5% and 7%
    assert (df["pct_of_workforce"] > 5.0).all()
    assert (df["pct_of_workforce"] < 7.0).all()


@pytest.mark.asyncio
async def test_fetch_unemployment_rate_quarterly(mock_source: MockInternalDataSource) -> None:
    """Verify quarterly unemployment rates covering 24 quarters."""
    df = await mock_source.fetch("unemployment_rate_quarterly")

    assert not df.empty
    assert len(df) == 24  # 6 years * 4 quarters

    expected_cols = {
        "quarter",
        "year",
        "period_start",
        "period_end",
        "overall_rate",
        "resident_rate",
        "citizen_rate",
        "youth_rate",
    }
    assert expected_cols.issubset(set(df.columns))

    # Overall rate between 1.5% and 4.0%
    assert (df["overall_rate"] >= 1.8).all()
    assert (df["overall_rate"] <= 3.6).all()

    # COVID peak in 2020 Q3
    q3_2020 = df[df["quarter"] == "2020-Q3"].iloc[0]
    assert q3_2020["overall_rate"] == 3.5
    assert q3_2020["resident_rate"] == 4.8


@pytest.mark.asyncio
async def test_fetch_median_gross_wages(mock_source: MockInternalDataSource) -> None:
    """Verify median gross wages by occupation group."""
    df = await mock_source.fetch("median_gross_wages")

    assert not df.empty
    assert len(df) >= 30  # 5 groups * 6+ years

    expected_cols = {
        "year",
        "period_start",
        "occupation_group",
        "median_monthly_wage_sgd",
        "yoy_growth",
    }
    assert expected_cols.issubset(set(df.columns))

    groups = set(df["occupation_group"].unique())
    assert groups == {"PMETs", "Clerical", "Service/Sales", "Production/Craft", "Cleaners/Laborers"}

    # PMETs wages higher than Clerical
    pmets_2024 = df[(df["occupation_group"] == "PMETs") & (df["year"] == 2024)][
        "median_monthly_wage_sgd"
    ].iloc[0]
    cleaners_2024 = df[(df["occupation_group"] == "Cleaners/Laborers") & (df["year"] == 2024)][
        "median_monthly_wage_sgd"
    ].iloc[0]
    assert pmets_2024 > cleaners_2024
    assert pmets_2024 == 7350


@pytest.mark.asyncio
async def test_fetch_business_registrations(mock_source: MockInternalDataSource) -> None:
    """Verify business registrations and cessations dataset."""
    df = await mock_source.fetch("business_registrations")

    assert not df.empty
    assert len(df) == 42  # 7 industries * 6 years

    expected_cols = {
        "year",
        "period_start",
        "industry",
        "new_company_registrations",
        "business_cessations",
        "net_formation",
    }
    assert expected_cols.issubset(set(df.columns))

    # Math check: new - cessations == net
    calculated_net = df["new_company_registrations"] - df["business_cessations"]
    assert (calculated_net == df["net_formation"]).all()


# ==============================================================================
# 4. Dataset Aliases and Error Handling Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_fetch_with_aliases(mock_source: MockInternalDataSource) -> None:
    """Dataset fetch works identically using aliases."""
    aliases = [
        ("employment_by_sector_2019_2024", "employment_by_sector"),
        ("ict_workforce_trends_2019_2024", "ict_workforce_trends"),
        ("unemployment_quarterly", "unemployment_rate_quarterly"),
        ("median_gross_wages_by_occupation", "median_gross_wages"),
        ("business_registrations_by_industry", "business_registrations"),
    ]
    for alias, canonical in aliases:
        df = await mock_source.fetch(alias)
        assert not df.empty, f"Alias {alias} returned empty DataFrame"
        assert df.attrs["dataset_id"] == canonical


@pytest.mark.asyncio
async def test_fetch_unknown_dataset_never_raises(mock_source: MockInternalDataSource) -> None:
    """Fetching an unknown dataset returns an empty DataFrame and does not raise."""
    df_unknown = await mock_source.fetch("non_existent_dataset_123")
    assert isinstance(df_unknown, pd.DataFrame)
    assert df_unknown.empty

    df_empty_str = await mock_source.fetch("")
    assert isinstance(df_empty_str, pd.DataFrame)
    assert df_empty_str.empty

    df_none = await mock_source.fetch(None)  # type: ignore
    assert isinstance(df_none, pd.DataFrame)
    assert df_none.empty


# ==============================================================================
# 5. Health Check Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_mock_source_health_check(mock_source: MockInternalDataSource) -> None:
    """Mock source health check always returns True."""
    assert await mock_source.health_check() is True
    assert await mock_source.safe_health_check(timeout=2.0) is True


# ==============================================================================
# 6. Auto-Registration in DataSourceRegistry Tests
# ==============================================================================


def test_mock_source_registered_in_singleton() -> None:
    """MockInternalDataSource is automatically registered in data_source_registry."""
    auto_register_sources()
    assert "mock_internal" in data_source_registry.list_all()

    source = data_source_registry.get("mock_internal")
    assert isinstance(source, MockInternalDataSource)
    assert source.source_id == "mock_internal"
