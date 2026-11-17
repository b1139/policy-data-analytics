"""Extended unit tests for SingStatDataSource to ensure comprehensive branch coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest

from app.core.config import settings
from app.data_sources.singstat import SingStatDataSource


@pytest.fixture
def singstat_ds() -> SingStatDataSource:
    return SingStatDataSource()


def test_get_headers_with_and_without_api_key(singstat_ds: SingStatDataSource):
    """Verify headers with and without SINGSTAT_API_KEY."""
    with patch.object(settings, "SINGSTAT_API_KEY", "test-secret-key"):
        headers = singstat_ds._get_headers()
        assert headers["Authorization"] == "Bearer test-secret-key"
        assert headers["api-key"] == "test-secret-key"

    with patch.object(settings, "SINGSTAT_API_KEY", ""):
        headers_no_key = singstat_ds._get_headers()
        assert "Authorization" not in headers_no_key
        assert "api-key" not in headers_no_key


@pytest.mark.asyncio
async def test_search_empty_and_list_keywords(singstat_ds: SingStatDataSource):
    """Verify search with empty keywords and list of strings."""
    with patch.object(settings, "USE_MOCK_DATA_SOURCES", False):
        res_empty = await singstat_ds.search("")
        assert res_empty == []

        res_spaces = await singstat_ds.search(["   ", ""])
        assert res_spaces == []


@pytest.mark.asyncio
async def test_search_mcp_success(singstat_ds: SingStatDataSource):
    """Verify search returns immediately if MCP search yields records."""
    mock_mcp_records = [
        {
            "id": "M123",
            "title": "MCP Table",
            "description": "Desc",
            "url": "http://test",
            "format": "json",
        }
    ]
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(singstat_ds, "_mcp_search", new=AsyncMock(return_value=mock_mcp_records)),
    ):
        results = await singstat_ds.search("economy")
        assert results == mock_mcp_records


@pytest.mark.asyncio
async def test_search_custom_client_and_item_parsing():
    """Verify search using custom_client and filtering of invalid records."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "records": [
                "not-a-dict",  # Should be skipped
                {"title": "No ID"},  # No id, should be skipped
                {"id": "M8101", "title": "Valid Table", "description": "Good", "format": "json"},
                {"tableId": "M8102", "title": "Second Valid", "format": "csv"},
            ]
        }
    }
    mock_client.get.return_value = mock_resp

    custom_ds = SingStatDataSource(client=mock_client)
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(custom_ds, "_mcp_search", new=AsyncMock(return_value=[])),
    ):
        results = await custom_ds.search(["employment", "trends"])
        assert len(results) == 2
        assert results[0]["id"] == "M8101"
        assert results[1]["id"] == "M8102"


@pytest.mark.asyncio
async def test_search_empty_records_with_mock_fallback_enabled_and_disabled(
    singstat_ds: SingStatDataSource,
):
    """Verify search behavior when live API returns no records."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"records": []}}

    # When fallback enabled
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", True),
        patch.object(singstat_ds, "_mcp_search", new=AsyncMock(return_value=[])),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)),
    ):
        res = await singstat_ds.search("nonexistent")
        assert isinstance(res, list)

    # When fallback disabled
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(singstat_ds, "_mcp_search", new=AsyncMock(return_value=[])),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)),
    ):
        res = await singstat_ds.search("nonexistent")
        assert res == []


@pytest.mark.asyncio
async def test_search_exception_with_mock_fallback_disabled(singstat_ds: SingStatDataSource):
    """Verify search error logging and empty return when fallback is disabled."""
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(settings, "USE_MOCK_DATA_AS_FALLBACK", False),
        patch.object(singstat_ds, "_mcp_search", new=AsyncMock(return_value=[])),
        patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Network dead")),
    ):
        res = await singstat_ds.search("economy")
        assert res == []


def test_mcp_enabled(singstat_ds: SingStatDataSource):
    """Verify _mcp_enabled honors custom client and settings."""
    with patch.object(settings, "SINGSTAT_MCP_ENABLED", True):
        assert singstat_ds._mcp_enabled() is True

    # Injected custom client disables MCP
    ds_with_client = SingStatDataSource(client=MagicMock())
    with patch.object(settings, "SINGSTAT_MCP_ENABLED", True):
        assert ds_with_client._mcp_enabled() is False

    with patch.object(settings, "SINGSTAT_MCP_ENABLED", False):
        assert singstat_ds._mcp_enabled() is False


@pytest.mark.asyncio
async def test_mcp_call_retry_backoff(singstat_ds: SingStatDataSource):
    """Verify _mcp_call retries and propagates error on exhausted retries."""
    with (
        patch.object(singstat_ds, "_mcp_call_once", side_effect=RuntimeError("MCP down")),
        patch("asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="MCP down"),
    ):
        await singstat_ds._mcp_call([("test", {})], retries=1)


@pytest.mark.asyncio
async def test_mcp_search_and_fetch_parsers(singstat_ds: SingStatDataSource):
    """Verify _mcp_search and _mcp_fetch parsing."""
    # Test _mcp_search with dictionary payload
    mcp_payload = {"data": [{"Total Employed Population": {"Annual": "T101"}}]}
    with (
        patch.object(singstat_ds, "_mcp_enabled", return_value=True),
        patch.object(singstat_ds, "_mcp_call", new=AsyncMock(return_value=[mcp_payload])),
    ):
        res = await singstat_ds._mcp_search("income")
        assert len(res) == 1
        assert res[0]["id"] == "T101"
        assert "Total Employed Population" in res[0]["title"]

    # Test _mcp_fetch with metadata and data payloads
    meta_payload = {
        "data": {
            "records": {
                "row": [{"seriesNo": "1", "rowText": "Total"}],
                "total": 50,
                "endPeriod": "2024",
            }
        }
    }
    data_payload = {
        "Data": {
            "row": [
                {
                    "rowText": "Total",
                    "columns": {"2023": "100", "2024": "110"},
                }
            ]
        }
    }
    with (
        patch.object(singstat_ds, "_mcp_enabled", return_value=True),
        patch.object(
            singstat_ds, "_mcp_call", new=AsyncMock(side_effect=[[meta_payload], [data_payload]])
        ),
    ):
        df = await singstat_ds._mcp_fetch("T101")
        assert df is not None
        assert len(df) == 2


@pytest.mark.asyncio
async def test_fetch_empty_invalid_id(singstat_ds: SingStatDataSource):
    """Verify fetch returns empty DataFrame for blank or non-string id."""
    df_empty = await singstat_ds.fetch("")
    assert df_empty.empty
    df_none = await singstat_ds.fetch(None)  # type: ignore[arg-type]
    assert df_none.empty


@pytest.mark.asyncio
async def test_fetch_via_mcp_success(singstat_ds: SingStatDataSource):
    """Verify fetch via MCP path returns finalized DataFrame."""
    dummy_df = pd.DataFrame([{"year": 2023, "value": 50}])
    with (
        patch.object(settings, "USE_MOCK_DATA_SOURCES", False),
        patch.object(singstat_ds, "_mcp_fetch", new=AsyncMock(return_value=dummy_df)),
    ):
        result = await singstat_ds.fetch("M9999")
        assert not result.empty
        assert "_source" in result.columns
        assert "_fetched_at" in result.columns


def test_parse_table_response_excel_and_csv(singstat_ds: SingStatDataSource):
    """Verify Excel, CSV, and invalid JSON responses in _parse_table_response."""
    # CSV content type
    resp_csv = MagicMock(spec=httpx.Response)
    resp_csv.headers = {"content-type": "text/csv"}
    resp_csv.text = "year,value\n2022,10\n2023,20"
    resp_csv.content = b"year,value\n2022,10\n2023,20"
    df_csv = singstat_ds._parse_table_response(resp_csv)
    assert df_csv is not None
    assert len(df_csv) == 2

    # Invalid JSON
    resp_bad_json = MagicMock(spec=httpx.Response)
    resp_bad_json.headers = {"content-type": "application/json"}
    resp_bad_json.text = "{invalid json"
    resp_bad_json.content = b"{invalid json"
    resp_bad_json.json.side_effect = ValueError("Bad JSON")
    assert singstat_ds._parse_table_response(resp_bad_json) is None


def test_parse_json_payload_variations(singstat_ds: SingStatDataSource):
    """Verify all branches of _parse_json_payload."""
    # Case 1a: Dict columns
    data_dict_cols = {
        "Data": {
            "row": [
                {
                    "rowText": "Total Employed",
                    "columns": {
                        "2023": "1,234.5",
                        "2024": "1,300",
                    },
                }
            ]
        }
    }
    df1 = singstat_ds._parse_json_payload(data_dict_cols)
    assert df1 is not None
    assert len(df1) == 2
    assert df1.iloc[0]["value"] == 1234.5

    # Case 1b: Nested columns list
    data_nested_cols = {
        "data": {
            "rows": [
                {
                    "series": "Resident",
                    "columns": [
                        {
                            "key": "2023 Q1",
                            "value": "na",  # Should be filtered out
                        },
                        {
                            "key": "2023 Q2",
                            "value": "500",
                            "columns": [{"key": "2023 Q2 Sub", "value": "250"}],
                        },
                    ],
                }
            ]
        }
    }
    df2 = singstat_ds._parse_json_payload(data_nested_cols)
    assert df2 is not None
    assert len(df2) == 2

    # Case 2: inner data is list
    data_inner_list = {"Data": [{"year": 2023, "val": 10}]}
    df3 = singstat_ds._parse_json_payload(data_inner_list)
    assert df3 is not None
    assert len(df3) == 1

    # Case 3: data is bare list
    df4 = singstat_ds._parse_json_payload([{"year": 2023, "val": 10}])
    assert df4 is not None
    assert len(df4) == 1


@pytest.mark.asyncio
async def test_fallback_fetch_mock_mapping_heuristics(singstat_ds: SingStatDataSource):
    """Verify keyword mapping heuristics in _fallback_fetch_mock."""
    # ICT keyword
    df_ict = await singstat_ds._fallback_fetch_mock("singstat_digital_workforce")
    assert not df_ict.empty

    # Unemployment keyword
    df_unemp = await singstat_ds._fallback_fetch_mock("singstat_jobless_rate")
    assert not df_unemp.empty

    # Wage keyword
    df_wage = await singstat_ds._fallback_fetch_mock("singstat_salary_index")
    assert not df_wage.empty

    # Business keyword
    df_biz = await singstat_ds._fallback_fetch_mock("singstat_company_acra")
    assert not df_biz.empty

    # Time filter applied
    df_filtered = await singstat_ds._fallback_fetch_mock(
        "singstat_salary_index", time_filter="2023"
    )
    assert not df_filtered.empty


@pytest.mark.asyncio
async def test_health_check_variations(singstat_ds: SingStatDataSource):
    """Verify health check logic with mock mode, custom client, and failure handling."""
    # 1. Mock mode
    with patch.object(settings, "USE_MOCK_DATA_SOURCES", True):
        assert await singstat_ds.health_check() is True

    # 2. Custom client success
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(status_code=200)
    mock_client.get.return_value = mock_resp
    custom_ds = SingStatDataSource(client=mock_client)

    with patch.object(settings, "USE_MOCK_DATA_SOURCES", False):
        assert await custom_ds.health_check() is True

    # 3. Custom client error
    mock_client.get.side_effect = httpx.ConnectTimeout("Timeout")
    with patch.object(settings, "USE_MOCK_DATA_SOURCES", False):
        assert await custom_ds.health_check() is False
