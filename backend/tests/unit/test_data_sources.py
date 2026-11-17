"""Unit tests for data sources and government connectors (Story S29).

Verifies:
- MockInternalDataSource.search() returns non-empty dataset list
- MockInternalDataSource.fetch() returns DataFrame with expected schema/columns
- SingStatDataSource with USE_MOCK_DATA_SOURCES=true returns mock data
- DataGovDataSource with USE_MOCK_DATA_SOURCES=true returns mock data
- Mock data source handles unknown dataset ids gracefully
"""

from unittest.mock import patch

import pandas as pd
import pytest

from app.core.config import settings
from app.data_sources.datagov import DataGovDataSource
from app.data_sources.mock_internal import MockInternalDataSource
from app.data_sources.singstat import SingStatDataSource


class TestDataSources:
    """Unit test suite for data source connectors and mock fallback."""

    @pytest.mark.asyncio
    async def test_mock_internal_search_returns_non_empty_list(self):
        """MockInternalDataSource.search() returns non-empty list for matching queries."""
        source = MockInternalDataSource()
        results = await source.search("employment")

        assert isinstance(results, list)
        assert len(results) > 0
        first = results[0]
        assert isinstance(first, dict)
        assert "id" in first
        assert "title" in first
        assert "employment" in first["id"].lower() or "employment" in first["title"].lower()

    @pytest.mark.asyncio
    async def test_mock_internal_fetch_returns_dataframe_with_correct_columns(self):
        """MockInternalDataSource.fetch() returns DataFrame with valid structure and columns."""
        source = MockInternalDataSource()
        df = await source.fetch("employment_by_sector")

        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        # Verify required columns exist
        expected_columns = {"year", "sector", "employment_count"}
        assert expected_columns.issubset(set(df.columns))
        # Verify metadata attached
        assert df.attrs.get("source") == "mock_internal"
        assert "dataset_id" in df.attrs

    @pytest.mark.asyncio
    async def test_singstat_with_mock_enabled_returns_mock_data(self):
        """SingStatDataSource returns mock dataset when USE_MOCK_DATA_SOURCES=True."""
        with patch.object(settings, "USE_MOCK_DATA_SOURCES", True):
            source = SingStatDataSource()

            # Search should return mock data catalog entries
            search_results = await source.search("employment")
            assert len(search_results) > 0
            assert any("employment" in r["title"].lower() for r in search_results)

            # Fetch should succeed with mock data without network calls
            df = await source.fetch("employment_by_sector")
            assert isinstance(df, pd.DataFrame)
            assert not df.empty
            assert "year" in df.columns
            assert "sector" in df.columns
            assert "_source" in df.columns
            assert (df["_source"] == "singstat").all()

    @pytest.mark.asyncio
    async def test_datagov_with_mock_enabled_returns_mock_data(self):
        """DataGovDataSource returns mock dataset when USE_MOCK_DATA_SOURCES=True."""
        with patch.object(settings, "USE_MOCK_DATA_SOURCES", True):
            source = DataGovDataSource()

            # Search returns mock datasets
            search_results = await source.search("wages")
            assert len(search_results) > 0

            # Fetch returns DataFrame
            df = await source.fetch("median_gross_wages")
            assert isinstance(df, pd.DataFrame)
            assert not df.empty
            assert "year" in df.columns
            assert "_source" in df.columns
            assert (df["_source"] == "datagov").all()

    @pytest.mark.asyncio
    async def test_mock_fetch_unknown_dataset_returns_empty_dataframe(self):
        """MockInternalDataSource.fetch() for non-existent dataset gracefully returns empty DataFrame."""
        source = MockInternalDataSource()
        df = await source.fetch("non_existent_dataset_id_12345")

        assert isinstance(df, pd.DataFrame)
        assert df.empty
