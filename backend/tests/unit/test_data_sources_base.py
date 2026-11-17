"""Unit tests for AbstractDataSource ABC and DataSourceRegistry (Story S16)."""

import asyncio
from typing import Any

import pandas as pd
import pytest

from app.data_sources.base import DEFAULT_HEALTH_CHECK_TIMEOUT, AbstractDataSource
from app.data_sources.registry import DataSourceRegistry, data_source_registry


class ConcreteTestSource(AbstractDataSource):
    """Concrete implementation for testing ABC contract and registry."""

    source_id = "test_source"
    display_name = "Test Data Source"

    def __init__(self, should_fail_fetch: bool = False, delay_health: float = 0.0) -> None:
        self.should_fail_fetch = should_fail_fetch
        self.delay_health = delay_health

    async def search(
        self,
        keywords: str | list[str],  # noqa: ARG002
        **filters: Any,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "ds_001",
                "title": "Employment by Sector 2019-2024",
                "description": "Annual employment counts across sectors in Singapore.",
                "url": "https://data.example.gov.sg/employment",
                "format": "csv",
            }
        ]

    async def fetch(self, dataset_id: str) -> pd.DataFrame:
        if self.should_fail_fetch:
            # Emulate internal error handled safely
            return pd.DataFrame()

        raw_df = pd.DataFrame(
            {
                " Sector Name ": ["Information & Communications", "Financial Services"],
                "Gross Wages (SGD)": [6500, 7200],
                "Record Date": ["2023-01-01", "2023-06-01"],
            }
        )
        return self.normalize_dataframe(
            raw_df,
            metadata={"source": self.source_id, "dataset_id": dataset_id, "industry": "ICT"},
        )

    async def health_check(self) -> bool:
        if self.delay_health > 0:
            await asyncio.sleep(self.delay_health)
        return not self.should_fail_fetch


class SecondTestSource(AbstractDataSource):
    """Second test data source for multi-source registry testing."""

    source_id = "mock_source_2"
    display_name = "Mock Source 2"

    async def search(
        self,
        keywords: str | list[str],  # noqa: ARG002
        **filters: Any,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return []

    async def fetch(self, dataset_id: str) -> pd.DataFrame:  # noqa: ARG002
        return pd.DataFrame()

    async def health_check(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure DataSourceRegistry is clean before and after each test."""
    registry = DataSourceRegistry()
    registry.clear()
    yield registry
    registry.clear()


# ==============================================================================
# 1. ABC Contract Tests
# ==============================================================================


def test_cannot_instantiate_abstract_base_class():
    """AbstractDataSource cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        AbstractDataSource()  # type: ignore


def test_subclass_missing_source_id_raises():
    """Subclass without source_id class attribute raises TypeError."""
    with pytest.raises(TypeError, match="must define a non-empty 'source_id'"):

        class InvalidSource1(AbstractDataSource):
            display_name = "Missing Source ID"

            async def search(self, keywords, **filters):  # noqa: ARG002
                return []

            async def fetch(self, dataset_id: str):  # noqa: ARG002
                return pd.DataFrame()

            async def health_check(self) -> bool:
                return True


def test_subclass_missing_display_name_raises():
    """Subclass without display_name class attribute raises TypeError."""
    with pytest.raises(TypeError, match="must define a non-empty 'display_name'"):

        class InvalidSource2(AbstractDataSource):
            source_id = "missing_display"

            async def search(self, keywords, **filters):  # noqa: ARG002
                return []

            async def fetch(self, dataset_id: str):  # noqa: ARG002
                return pd.DataFrame()

            async def health_check(self) -> bool:
                return True


def test_subclass_missing_methods_raises():
    """Subclass missing abstract methods cannot be instantiated."""

    class IncompleteSource(AbstractDataSource):
        source_id = "incomplete"
        display_name = "Incomplete Source"

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteSource()  # type: ignore


def test_concrete_subclass_instantiation():
    """Valid concrete subclass instantiates with correct attributes."""
    source = ConcreteTestSource()
    assert source.source_id == "test_source"
    assert source.display_name == "Test Data Source"


# ==============================================================================
# 2. DataSourceRegistry Tests
# ==============================================================================


def test_registry_singleton_identity():
    """DataSourceRegistry always returns the exact same singleton instance."""
    reg1 = DataSourceRegistry()
    reg2 = DataSourceRegistry()
    assert reg1 is reg2
    assert reg1 is data_source_registry


def test_register_and_get():
    """Registration and retrieval by source_id."""
    registry = DataSourceRegistry()
    source = ConcreteTestSource()
    registry.register(source)

    retrieved = registry.get("test_source")
    assert retrieved is source
    assert "test_source" in registry
    assert len(registry) == 1
    assert registry.list_all() == ["test_source"]


def test_register_multiple_sources():
    """Multiple sources can be registered and listed in sorted order."""
    registry = DataSourceRegistry()
    s1 = ConcreteTestSource()
    s2 = SecondTestSource()

    registry.register(s1)
    registry.register(s2)

    assert registry.list_all() == ["mock_source_2", "test_source"]
    assert len(registry) == 2
    all_sources = registry.get_all()
    assert all_sources["test_source"] is s1
    assert all_sources["mock_source_2"] is s2


def test_get_nonexistent_source_raises_key_error():
    """Requesting an unregistered source raises KeyError with helpful message."""
    registry = DataSourceRegistry()
    with pytest.raises(KeyError) as exc_info:
        registry.get("unknown_source")

    assert "Data source 'unknown_source' not found in registry" in str(exc_info.value)


def test_register_duplicate_with_overwrite_default():
    """Registering duplicate source with overwrite=True (default) updates the instance."""
    registry = DataSourceRegistry()
    s1 = ConcreteTestSource()
    s2 = ConcreteTestSource()

    registry.register(s1)
    assert registry.get("test_source") is s1

    # Overwrite by default
    registry.register(s2)
    assert registry.get("test_source") is s2
    assert len(registry) == 1


def test_register_duplicate_with_overwrite_false_raises():
    """Registering duplicate source with overwrite=False raises ValueError."""
    registry = DataSourceRegistry()
    s1 = ConcreteTestSource()
    s2 = ConcreteTestSource()

    registry.register(s1)
    with pytest.raises(ValueError, match="already registered and overwrite is False"):
        registry.register(s2, overwrite=False)


def test_register_invalid_type_raises():
    """Attempting to register non-AbstractDataSource object raises TypeError."""
    registry = DataSourceRegistry()
    with pytest.raises(TypeError, match="Expected instance of AbstractDataSource"):
        registry.register("not_a_source")  # type: ignore


def test_unregister_and_clear():
    """Unregister removes single source; clear removes all sources."""
    registry = DataSourceRegistry()
    s1 = ConcreteTestSource()
    s2 = SecondTestSource()

    registry.register(s1)
    registry.register(s2)
    assert len(registry) == 2

    assert registry.unregister("test_source") is True
    assert "test_source" not in registry
    assert registry.unregister("test_source") is False
    assert len(registry) == 1

    registry.clear()
    assert len(registry) == 0
    assert registry.list_all() == []


def test_registry_iteration():
    """Registry supports iteration over registered source IDs."""
    registry = DataSourceRegistry()
    registry.register(ConcreteTestSource())
    registry.register(SecondTestSource())

    ids = list(registry)
    assert "test_source" in ids
    assert "mock_source_2" in ids


# ==============================================================================
# 3. DataFrame Normalization Tests
# ==============================================================================


def test_column_name_normalization():
    """Column names are cleaned: lowercase, spaces/dashes to underscores, symbols removed."""
    raw = pd.DataFrame(
        {
            " Sector Name ": ["ICT"],
            "Gross Monthly Income (SGD)": [5000],
            "YoY-Growth / Rate": [0.05],
            "Data..Col___Name": [1],
            "Special!#&*Chars": [10],
        }
    )

    cleaned = AbstractDataSource.normalize_dataframe(raw)
    expected_cols = [
        "sector_name",
        "gross_monthly_income_sgd",
        "yoy_growth_rate",
        "data_col_name",
        "specialchars",
    ]
    assert list(cleaned.columns) == expected_cols


def test_datetime_localization_to_utc():
    """Timezone-naive datetime columns are localized to UTC."""
    raw = pd.DataFrame(
        {
            "sector": ["Tech"],
            "timestamp": pd.to_datetime(["2024-01-01 10:00:00"]),
        }
    )
    normalized = AbstractDataSource.normalize_dataframe(raw)
    assert normalized["timestamp"].dt.tz is not None
    assert str(normalized["timestamp"].dt.tz) == "UTC"


def test_datetime_conversion_to_utc():
    """Timezone-aware datetime columns are converted to UTC."""
    raw = pd.DataFrame(
        {
            "sector": ["Tech"],
            "timestamp": pd.to_datetime(["2024-01-01 18:00:00+08:00"]),
        }
    )
    normalized = AbstractDataSource.normalize_dataframe(raw)
    assert str(normalized["timestamp"].dt.tz) == "UTC"
    assert normalized["timestamp"].iloc[0].hour == 10  # 18:00 SGT = 10:00 UTC


def test_date_string_parsing_to_utc():
    """String columns with date names are automatically parsed to UTC datetimes."""
    raw = pd.DataFrame(
        {
            "record_date": ["2023-05-01", "2023-06-01"],
            "value": [100, 200],
        }
    )
    normalized = AbstractDataSource.normalize_dataframe(raw)
    assert pd.api.types.is_datetime64_any_dtype(normalized["record_date"])
    assert str(normalized["record_date"].dt.tz) == "UTC"


def test_empty_dataframe_normalization():
    """Empty DataFrame normalization attaches metadata without error."""
    empty_df = pd.DataFrame()
    meta = {"source": "test", "dataset_id": "empty_ds"}
    normalized = AbstractDataSource.normalize_dataframe(empty_df, metadata=meta)
    assert normalized.empty
    assert normalized.attrs["source"] == "test"
    assert normalized.attrs["dataset_id"] == "empty_ds"


def test_metadata_attached_to_attrs():
    """Source metadata is properly attached to df.attrs."""
    raw = pd.DataFrame({"col": [1, 2]})
    meta = {
        "source": "singstat",
        "dataset_id": "M810001",
        "url": "https://tablebuilder.singstat.gov.sg/api/table/M810001",
        "industry": "Information & Communications",
    }
    normalized = AbstractDataSource.normalize_dataframe(raw, metadata=meta)
    assert normalized.attrs["source"] == "singstat"
    assert normalized.attrs["dataset_id"] == "M810001"
    assert normalized.attrs["industry"] == "Information & Communications"
    assert "fetched_at" in normalized.attrs


# ==============================================================================
# 4. Search and Safe Fetch Contract Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_search_contract_schema():
    """search() returns list of dicts with id, title, description, url, format."""
    source = ConcreteTestSource()
    results = await source.search("employment", industry="ICT")

    assert isinstance(results, list)
    assert len(results) > 0
    item = results[0]
    for required_key in ["id", "title", "description", "url", "format"]:
        assert required_key in item, f"Missing required key '{required_key}' in search result"


@pytest.mark.asyncio
async def test_fetch_returns_normalized_dataframe():
    """fetch() returns a normalized DataFrame with metadata."""
    source = ConcreteTestSource()
    df = await source.fetch("ds_001")

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "sector_name" in df.columns
    assert "gross_wages_sgd" in df.columns
    assert df.attrs["source"] == "test_source"
    assert df.attrs["dataset_id"] == "ds_001"


@pytest.mark.asyncio
async def test_fetch_never_raises_on_error():
    """fetch() returns empty DataFrame on failure and never raises unhandled exception."""
    failing_source = ConcreteTestSource(should_fail_fetch=True)
    df = await failing_source.fetch("bad_id")

    assert isinstance(df, pd.DataFrame)
    assert df.empty


# ==============================================================================
# 5. Health Check Timeout Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_health_check_healthy():
    """health_check returns True for responsive source."""
    source = ConcreteTestSource()
    assert await source.health_check() is True
    assert await source.safe_health_check(timeout=DEFAULT_HEALTH_CHECK_TIMEOUT) is True


@pytest.mark.asyncio
async def test_health_check_failing():
    """health_check returns False for unresponsive source."""
    source = ConcreteTestSource(should_fail_fetch=True)
    assert await source.health_check() is False
    assert await source.safe_health_check() is False


@pytest.mark.asyncio
async def test_safe_health_check_timeout():
    """safe_health_check enforces 5-second timeout and returns False if exceeded."""
    slow_source = ConcreteTestSource(delay_health=10.0)
    # Test with small timeout (0.05s) to verify timeout behavior without slowing down tests
    result = await slow_source.safe_health_check(timeout=0.05)
    assert result is False
