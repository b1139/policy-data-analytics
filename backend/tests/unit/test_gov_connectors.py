"""Unit tests for SingStat and Data.gov.sg connectors (Story S17).

Verifies:
- AbstractDataSource contract conformance for SingStatDataSource and DataGovDataSource
- Live HTTP request formatting and response parsing (JSON and CSV formats)
- Column normalization, UTC timestamps, and addition of '_source' and '_fetched_at' columns
- Graceful degradation and fallback to MockInternalDataSource on HTTP error, timeouts,
  empty results, and when USE_MOCK_DATA_SOURCES=True
- Optional Bearer token handling for Data.gov.sg (DATAGOV_API_TOKEN)
- Health check endpoints and timeouts
- Automatic registration in DataSourceRegistry
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

from app.core.config import settings
from app.data_sources import (
    DataGovDataSource,
    SingStatDataSource,
    auto_register_sources,
    data_source_registry,
)

# ==============================================================================
# 1. SingStat Connector Unit Tests
# ==============================================================================


@pytest.fixture
def singstat_source() -> SingStatDataSource:
    """Fixture providing a SingStatDataSource instance."""
    return SingStatDataSource()


def test_singstat_attributes(singstat_source: SingStatDataSource) -> None:
    """Verify class attributes and contract compliance."""
    assert singstat_source.source_id == "singstat"
    assert singstat_source.display_name == "SingStat Table Builder"


@pytest.mark.asyncio
async def test_singstat_search_live_success(singstat_source: SingStatDataSource) -> None:
    """Verify parsing of successful SingStat Table Builder search response."""
    mock_payload = {
        "status": "success",
        "data": {
            "records": [
                {
                    "id": "M810611",
                    "title": "Employed Residents Aged 15 Years And Over By Industry",
                    "description": "Annual breakdown of employed resident workforce",
                    "theme": "Economy",
                    "format": "json",
                },
                {
                    "id": "M810622",
                    "title": "ICT Workforce Statistics",
                    "description": "Information and Communications manpower statistics",
                    "format": "csv",
                },
            ]
        },
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_payload,
        request=httpx.Request("GET", "https://tablebuilder.singstat.gov.sg/api/table/search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await singstat_source.search("employment ICT")

    assert len(results) == 2
    assert results[0]["id"] == "M810611"
    assert results[0]["title"] == "Employed Residents Aged 15 Years And Over By Industry"
    assert "https://tablebuilder.singstat.gov.sg/table/M810611" in results[0]["url"]
    assert results[0]["format"] == "json"

    assert results[1]["id"] == "M810622"
    assert results[1]["format"] == "csv"


@pytest.mark.asyncio
async def test_singstat_search_with_format_filter(singstat_source: SingStatDataSource) -> None:
    """Verify search respects optional format filter parameter."""
    mock_payload = {
        "data": [
            {"id": "T1", "title": "Table 1", "format": "csv"},
            {"id": "T2", "title": "Table 2", "format": "json"},
        ]
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_payload,
        request=httpx.Request("GET", "https://tablebuilder.singstat.gov.sg/api/table/search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await singstat_source.search("test", format="csv")

    assert len(results) == 1
    assert results[0]["id"] == "T1"


@pytest.mark.asyncio
async def test_singstat_search_empty_query(singstat_source: SingStatDataSource) -> None:
    """Empty search query returns empty list without making HTTP call."""
    results = await singstat_source.search("")
    assert results == []

    results_list = await singstat_source.search(["", "  "])
    assert results_list == []


@pytest.mark.asyncio
async def test_singstat_search_fallback_on_http_error(singstat_source: SingStatDataSource) -> None:
    """When SingStat search encounters HTTP error or timeout and USE_MOCK_DATA_AS_FALLBACK=True, falls back to MockInternalDataSource."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")),
    ):
        results = await singstat_source.search("employment")

    assert len(results) > 0
    # Mock data catalog should have matched employment datasets
    ids = [r["id"] for r in results]
    assert any("employment" in i for i in ids)


@pytest.mark.asyncio
async def test_singstat_search_no_fallback_when_disabled(
    singstat_source: SingStatDataSource,
) -> None:
    """When USE_MOCK_DATA_AS_FALLBACK=False (default), SingStat search returns empty list on HTTP error without mock data."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")),
    ):
        results = await singstat_source.search("employment")

    assert results == []


@pytest.mark.asyncio
async def test_singstat_search_fallback_when_mock_mode_enabled(
    singstat_source: SingStatDataSource,
) -> None:
    """When USE_MOCK_DATA_SOURCES is True, directly falls back to mock without network calls."""
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", True),
        patch("httpx.AsyncClient.get") as mock_http_get,
    ):
        results = await singstat_source.search("ict")
        assert not mock_http_get.called
        assert len(results) > 0
        assert any("ict" in r["id"].lower() for r in results)


@pytest.mark.asyncio
async def test_singstat_fetch_json_hierarchical(singstat_source: SingStatDataSource) -> None:
    """Verify parsing SingStat Table Builder hierarchical JSON rows into DataFrame."""
    mock_payload = {
        "data": {
            "id": "M810611",
            "title": "Resident Employment by Sector",
            "row": [
                {
                    "rowText": "Manufacturing",
                    "columns": [
                        {"key": "2021", "value": "450.2"},
                        {"key": "2022", "value": "462.5"},
                    ],
                },
                {
                    "rowText": "Information & Communications",
                    "columns": [
                        {"key": "2021", "value": "130.4"},
                        {"key": "2022", "value": "145.8"},
                    ],
                },
            ],
        }
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_payload,
        request=httpx.Request(
            "GET", "https://tablebuilder.singstat.gov.sg/api/table/tabledata/M810611"
        ),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await singstat_source.fetch("M810611")

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) == 4

    # Check normalized column names
    assert "series" in df.columns
    assert "period" in df.columns
    assert "value" in df.columns

    # Check audit columns
    assert "_source" in df.columns
    assert df["_source"].iloc[0] == "singstat"
    assert "_fetched_at" in df.columns

    # Check attrs metadata
    assert df.attrs["source"] == "singstat"
    assert df.attrs["dataset_id"] == "M810611"


@pytest.mark.asyncio
async def test_singstat_fetch_csv_response(singstat_source: SingStatDataSource) -> None:
    """Verify parsing CSV formatted response from SingStat."""
    csv_content = (
        "Year,Industry Sector,Employment Count SGD\n"
        "2022,Technology Services,125000\n"
        "2023,Technology Services,138000\n"
    )

    mock_response = httpx.Response(
        status_code=200,
        text=csv_content,
        headers={"content-type": "text/csv"},
        request=httpx.Request(
            "GET", "https://tablebuilder.singstat.gov.sg/api/table/tabledata/M999"
        ),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await singstat_source.fetch("M999")

    assert not df.empty
    assert len(df) == 2

    # Check lowercase normalized column names
    expected_cols = {"year", "industry_sector", "employment_count_sgd", "_source", "_fetched_at"}
    assert expected_cols.issubset(set(df.columns))
    assert (df["_source"] == "singstat").all()


@pytest.mark.asyncio
async def test_singstat_fetch_empty_id_returns_empty(singstat_source: SingStatDataSource) -> None:
    """Empty or None dataset_id returns empty DataFrame without raising."""
    df_empty = await singstat_source.fetch("")
    assert isinstance(df_empty, pd.DataFrame)
    assert df_empty.empty

    df_spaces = await singstat_source.fetch("   ")
    assert df_spaces.empty


@pytest.mark.asyncio
async def test_singstat_fetch_fallback_on_http_error(singstat_source: SingStatDataSource) -> None:
    """When SingStat fetch fails with HTTP error and USE_MOCK_DATA_AS_FALLBACK=True, falls back to MockInternalDataSource."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.HTTPStatusError(
                "404 Not Found", request=MagicMock(), response=MagicMock()
            ),
        ),
    ):
        df = await singstat_source.fetch("employment_by_sector")

    assert not df.empty
    assert "_source" in df.columns
    assert df["_source"].iloc[0] == "singstat"
    assert "_fetched_at" in df.columns
    assert df.attrs["fallback"] is True


@pytest.mark.asyncio
async def test_singstat_fetch_no_fallback_when_disabled(
    singstat_source: SingStatDataSource,
) -> None:
    """When USE_MOCK_DATA_AS_FALLBACK=False (default), SingStat fetch returns empty DataFrame on HTTP error."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.HTTPStatusError(
                "404 Not Found", request=MagicMock(), response=MagicMock()
            ),
        ),
    ):
        df = await singstat_source.fetch("employment_by_sector")

    assert df.empty


@pytest.mark.asyncio
async def test_singstat_fetch_external_id_fallback_mapping(
    singstat_source: SingStatDataSource,
) -> None:
    """When external ID fails and USE_MOCK_DATA_AS_FALLBACK=True, fallback maps to a realistic mock dataset and succeeds."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Timeout")),
    ):
        df = await singstat_source.fetch("M_UNKNOWN_ICT_WORKFORCE")

    assert not df.empty
    assert "_source" in df.columns
    assert "_fetched_at" in df.columns
    assert df.attrs["requested_id"] == "M_UNKNOWN_ICT_WORKFORCE"
    # Mapped to ict_workforce_trends
    assert "ict_headcount" in df.columns or "employment_count" in df.columns


@pytest.mark.asyncio
async def test_singstat_health_check_success(singstat_source: SingStatDataSource) -> None:
    """Health check returns True when SingStat endpoint returns HTTP 200."""
    mock_resp = httpx.Response(
        status_code=200, request=httpx.Request("GET", singstat_source.HEALTH_CHECK_URL)
    )
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", return_value=mock_resp),
    ):
        assert await singstat_source.health_check() is True


@pytest.mark.asyncio
async def test_singstat_health_check_failure(singstat_source: SingStatDataSource) -> None:
    """Health check returns False when SingStat endpoint fails or times out."""
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Timeout")),
    ):
        assert await singstat_source.health_check() is False


@pytest.mark.asyncio
async def test_singstat_health_check_in_mock_mode(singstat_source: SingStatDataSource) -> None:
    """Health check returns True immediately when USE_MOCK_DATA_SOURCES is True."""
    with patch.object(settings, "USE_MOCK_DATA_SOURCES", True):
        assert await singstat_source.health_check() is True


# ==============================================================================
# 2. Data.gov.sg Connector Unit Tests
# ==============================================================================


@pytest.fixture
def datagov_source() -> DataGovDataSource:
    """Fixture providing a DataGovDataSource instance."""
    return DataGovDataSource()


def test_datagov_attributes(datagov_source: DataGovDataSource) -> None:
    """Verify class attributes and contract compliance."""
    assert datagov_source.source_id == "datagov"
    assert datagov_source.display_name == "Data.gov.sg"


def test_datagov_headers_with_token(datagov_source: DataGovDataSource) -> None:
    """Verify Authorization Bearer token header is added when DATAGOV_API_TOKEN is set."""
    with patch.object(settings, "DATAGOV_API_TOKEN", "test-token-12345"):
        headers = datagov_source._get_headers()
        assert headers["Authorization"] == "Bearer test-token-12345"

    with patch.object(settings, "DATAGOV_API_TOKEN", None):
        headers_no_token = datagov_source._get_headers()
        assert "Authorization" not in headers_no_token


@pytest.mark.asyncio
async def test_datagov_search_live_success(datagov_source: DataGovDataSource) -> None:
    """Verify parsing CKAN package_search results."""
    mock_payload = {
        "help": "https://data.gov.sg/api/3/action/help_show?name=package_search",
        "success": True,
        "result": {
            "count": 2,
            "results": [
                {
                    "id": "pkg-001",
                    "name": "employment-by-industry-annual",
                    "title": "Employment by Industry (Annual)",
                    "notes": "Statistics on annual resident employment by industry sector.",
                    "resources": [
                        {
                            "id": "res-uuid-111",
                            "name": "Employment Data 2019-2024",
                            "format": "CSV",
                            "url": "https://data.gov.sg/dataset/res-uuid-111/download",
                        }
                    ],
                },
                {
                    "id": "pkg-002",
                    "name": "wages-by-occupation",
                    "title": "Median Gross Wages by Occupation",
                    "notes": "Occupational wage benchmarks in Singapore.",
                    "resources": [],
                },
            ],
        },
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_payload,
        request=httpx.Request("GET", "https://data.gov.sg/api/action/package_search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        results = await datagov_source.search("employment wages")

    assert len(results) == 2
    # Resource id should be prioritized as the dataset identifier
    assert results[0]["id"] == "res-uuid-111"
    assert results[0]["title"] == "Employment by Industry (Annual)"
    assert results[0]["format"] == "csv"

    # When no resource exists, fallback to package id/name
    assert results[1]["id"] == "pkg-002"
    assert results[1]["title"] == "Median Gross Wages by Occupation"


@pytest.mark.asyncio
async def test_datagov_search_fallback_on_failure(datagov_source: DataGovDataSource) -> None:
    """When DataGov search fails and USE_MOCK_DATA_AS_FALLBACK=True, falls back gracefully to MockInternalDataSource."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")),
    ):
        results = await datagov_source.search("unemployment")

    assert len(results) > 0
    assert any("unemployment" in r["id"].lower() for r in results)


@pytest.mark.asyncio
async def test_datagov_search_no_fallback_when_disabled(datagov_source: DataGovDataSource) -> None:
    """When USE_MOCK_DATA_AS_FALLBACK=False (default), DataGov search returns empty list on failure."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")),
    ):
        results = await datagov_source.search("unemployment")

    assert results == []


@pytest.mark.asyncio
async def test_datagov_search_mock_mode(datagov_source: DataGovDataSource) -> None:
    """When USE_MOCK_DATA_SOURCES is True, DataGov search uses mock directly."""
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", True),
        patch("httpx.AsyncClient.get") as mock_get,
    ):
        results = await datagov_source.search("wages")
        assert not mock_get.called
        assert len(results) > 0


@pytest.mark.asyncio
async def test_datagov_fetch_json_records(datagov_source: DataGovDataSource) -> None:
    """Verify parsing Data.gov.sg CKAN datastore_search JSON records into DataFrame."""
    mock_payload = {
        "help": "https://data.gov.sg/api/3/action/help_show?name=datastore_search",
        "success": True,
        "result": {
            "resource_id": "res-uuid-111",
            "fields": [
                {"id": "_id", "type": "int4"},
                {"id": "Year", "type": "text"},
                {"id": "Sector", "type": "text"},
            ],
            "records": [
                {"_id": 1, "Year": 2022, "Sector": "Infocomm Technology", "Headcount": 120500},
                {"_id": 2, "Year": 2023, "Sector": "Infocomm Technology", "Headcount": 131200},
            ],
            "total": 2,
        },
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_payload,
        request=httpx.Request("GET", "https://data.gov.sg/api/action/datastore_search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await datagov_source.fetch("res-uuid-111")

    assert not df.empty
    assert len(df) == 2

    # Column normalization check (leading underscore in _id stripped by clean_column_name)
    expected_cols = {"id", "year", "sector", "headcount", "_source", "_fetched_at"}
    assert expected_cols.issubset(set(df.columns))

    # Audit columns
    assert (df["_source"] == "datagov").all()
    assert df.attrs["source"] == "datagov"
    assert df.attrs["dataset_id"] == "res-uuid-111"


@pytest.mark.asyncio
async def test_datagov_fetch_csv_resource(datagov_source: DataGovDataSource) -> None:
    """Verify parsing Data.gov.sg CSV response directly."""
    csv_data = "Quarter,Citizen Unemployment Rate,Resident Unemployment Rate\n2023-Q1,2.8,2.7\n2023-Q2,2.7,2.6\n"
    mock_response = httpx.Response(
        status_code=200,
        text=csv_data,
        headers={"content-type": "text/csv"},
        request=httpx.Request("GET", "https://data.gov.sg/api/action/datastore_search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await datagov_source.fetch("res-unemp-csv")

    assert not df.empty
    assert len(df) == 2
    assert "citizen_unemployment_rate" in df.columns
    assert (df["_source"] == "datagov").all()


@pytest.mark.asyncio
async def test_datagov_fetch_fallback_on_http_error(datagov_source: DataGovDataSource) -> None:
    """When DataGov fetch fails with 500 or timeout and USE_MOCK_DATA_AS_FALLBACK=True, falls back to MockInternalDataSource."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch("httpx.AsyncClient.get", side_effect=httpx.HTTPError("Service Unavailable")),
    ):
        df = await datagov_source.fetch("business_registrations")

    assert not df.empty
    assert (df["_source"] == "datagov").all()
    assert "_fetched_at" in df.columns
    assert df.attrs["fallback"] is True


@pytest.mark.asyncio
async def test_datagov_fetch_no_fallback_when_disabled(datagov_source: DataGovDataSource) -> None:
    """When USE_MOCK_DATA_AS_FALLBACK=False (default), DataGov fetch returns empty DataFrame on HTTP error."""
    with (
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", side_effect=httpx.HTTPError("Service Unavailable")),
    ):
        df = await datagov_source.fetch("business_registrations")

    assert df.empty


@pytest.mark.asyncio
async def test_datagov_fetch_empty_id(datagov_source: DataGovDataSource) -> None:
    """Empty dataset_id returns empty DataFrame without raising."""
    df = await datagov_source.fetch("")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@pytest.mark.asyncio
async def test_datagov_health_check_success(datagov_source: DataGovDataSource) -> None:
    """Health check returns True when Data.gov.sg responds with HTTP 200."""
    mock_resp = httpx.Response(
        status_code=200, request=httpx.Request("GET", datagov_source.HEALTH_CHECK_URL)
    )
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", return_value=mock_resp),
    ):
        assert await datagov_source.health_check() is True


@pytest.mark.asyncio
async def test_datagov_health_check_failure(datagov_source: DataGovDataSource) -> None:
    """Health check returns False when Data.gov.sg is down or throws error."""
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")),
    ):
        assert await datagov_source.health_check() is False


@pytest.mark.asyncio
async def test_datagov_fetch_excel_resource(datagov_source: DataGovDataSource) -> None:
    """Verify parsing Data.gov.sg Excel (.xlsx) spreadsheet into DataFrame."""
    excel_df = pd.DataFrame(
        {
            "Year": [2022, 2023, 2024],
            "Sector": ["Finance", "Finance", "Finance"],
            "Employment": [150000, 155000, 160000],
        }
    )
    buffer = io.BytesIO()
    excel_df.to_excel(buffer, index=False, engine="openpyxl")
    excel_bytes = buffer.getvalue()

    mock_response = httpx.Response(
        status_code=200,
        content=excel_bytes,
        headers={
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
        request=httpx.Request("GET", "https://data.gov.sg/api/action/datastore_search"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await datagov_source.fetch("res-finance-xlsx")

    assert not df.empty
    assert len(df) == 3
    assert "employment" in df.columns
    assert (df["_source"] == "datagov").all()


@pytest.mark.asyncio
async def test_singstat_fetch_excel_resource(singstat_source: SingStatDataSource) -> None:
    """Verify parsing SingStat Excel (.xlsx) spreadsheet into DataFrame."""
    excel_df = pd.DataFrame(
        {
            "Year": [2021, 2022, 2023],
            "Metric": ["GDP Growth", "GDP Growth", "GDP Growth"],
            "Value": [7.6, 3.6, 1.1],
        }
    )
    buffer = io.BytesIO()
    excel_df.to_excel(buffer, index=False, engine="openpyxl")
    excel_bytes = buffer.getvalue()

    mock_response = httpx.Response(
        status_code=200,
        content=excel_bytes,
        headers={
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
        request=httpx.Request(
            "GET", "https://tablebuilder.singstat.gov.sg/api/table/tabledata/T123"
        ),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        df = await singstat_source.fetch("T123")

    assert not df.empty
    assert len(df) == 3
    assert "value" in df.columns
    assert (df["_source"] == "singstat").all()


# ==============================================================================
# 3. Registry Integration Tests
# ==============================================================================


def test_registry_contains_both_connectors() -> None:
    """DataSourceRegistry auto-registers singstat, datagov, and mock_internal connectors."""
    auto_register_sources()

    registered_ids = data_source_registry.list_all()
    assert "singstat" in registered_ids
    assert "datagov" in registered_ids
    assert "mock_internal" in registered_ids

    singstat = data_source_registry.get("singstat")
    assert isinstance(singstat, SingStatDataSource)
    assert singstat.source_id == "singstat"

    datagov = data_source_registry.get("datagov")
    assert isinstance(datagov, DataGovDataSource)
    assert datagov.source_id == "datagov"
