"""Unit tests for Data Quality & Validation Pipeline (Story S19).

Tests:
1. ValidationResult schema structure, defaults, and analysis metadata export.
2. DataQualityValidator:
   - Empty DataFrame check (immediate failed result with error message).
   - Null check (> 10% null flagged as warning).
   - Type consistency & string contamination check.
   - Date range sanity check (1990–2030).
   - Outlier detection (> 3 IQR from median).
   - Non-destructive execution and `flag_dataframe` with `_dq_flag` column.
   - Non-raising error handling on unexpected inputs.
3. DataService:
   - `fetch_and_validate` with valid mock source.
   - `fetch_and_validate` with invalid/unregistered source.
   - `cache_dataset` with SHA-256 fingerprint deduplication.
   - `attach_quality_to_metadata` analysis metadata integration.
"""

import hashlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
from app.models.dataset import Dataset
from app.schemas.data_quality import ValidationResult
from app.services.data_service import (
    DataQualityValidator,
    DataService,
    data_service,
)


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session for caching tests."""
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
def validator() -> DataQualityValidator:
    """Provide a DataQualityValidator instance."""
    return DataQualityValidator()


# ---------------------------------------------------------------------------
# 1. ValidationResult Schema Tests
# ---------------------------------------------------------------------------


def test_validation_result_schema_defaults() -> None:
    """Test ValidationResult field types and default factory lists."""
    result = ValidationResult(passed=True)
    assert result.passed is True
    assert result.warnings == []
    assert result.errors == []
    assert result.stats == {}


def test_validation_result_to_analysis_metadata() -> None:
    """Test conversion of ValidationResult to metadata dictionary format."""
    result = ValidationResult(
        passed=False,
        warnings=["Column 'wage' has 12.0% missing values"],
        errors=["Empty structure"],
        stats={"row_count": 10, "col_count": 2},
    )
    metadata = result.to_analysis_metadata()
    assert metadata["passed"] is False
    assert len(metadata["data_quality_issues"]) == 2
    assert "Column 'wage' has 12.0% missing values" in metadata["data_quality_issues"]
    assert "Empty structure" in metadata["data_quality_issues"]
    assert metadata["stats"]["row_count"] == 10


# ---------------------------------------------------------------------------
# 2. DataQualityValidator Tests
# ---------------------------------------------------------------------------


def test_validate_empty_dataframe(validator: DataQualityValidator) -> None:
    """Test empty DataFrame immediately returns failed result with error."""
    # Completely empty DataFrame
    res1 = validator.validate(pd.DataFrame())
    assert res1.passed is False
    assert len(res1.errors) > 0
    assert "empty" in res1.errors[0].lower()
    assert res1.stats["row_count"] == 0

    # DataFrame with columns but 0 rows
    res2 = validator.validate(pd.DataFrame({"a": [], "b": []}))
    assert res2.passed is False
    assert len(res2.errors) > 0

    # None DataFrame
    res3 = validator.validate(None)  # type: ignore[arg-type]
    assert res3.passed is False
    assert len(res3.errors) > 0


def test_validate_null_check(validator: DataQualityValidator) -> None:
    """Test null check flags columns exceeding 10% threshold."""
    # 20 rows: col_clean has 0 nulls (0%), col_border has 2 nulls (10%), col_dirty has 4 nulls (20%)
    df = pd.DataFrame(
        {
            "col_clean": [1.0] * 20,
            "col_border": [1.0] * 18 + [np.nan, np.nan],  # 10% null
            "col_dirty": [1.0] * 16 + [np.nan] * 4,  # 20% null (> 10%)
        }
    )

    result = validator.validate(df)
    assert result.passed is True  # Non-destructive warning does not fail validation
    assert len(result.errors) == 0

    # Verify col_dirty flagged in warnings, but not col_clean or col_border
    dirty_warnings = [w for w in result.warnings if "col_dirty" in w]
    assert len(dirty_warnings) == 1
    assert "20.0%" in dirty_warnings[0]

    assert not any("col_clean" in w for w in result.warnings)
    assert not any("col_border" in w for w in result.warnings)

    # Check stats
    assert result.stats["null_pct_by_col"]["col_dirty"] == 0.2
    assert result.stats["null_pct_by_col"]["col_border"] == 0.1
    assert result.stats["null_pct_by_col"]["col_clean"] == 0.0


def test_validate_type_consistency_string_contamination(
    validator: DataQualityValidator,
) -> None:
    """Test detection of numeric-looking columns contaminated with string values."""
    # Column with predominantly numbers but contaminated by strings
    df = pd.DataFrame(
        {
            "clean_numeric": [10, 20, 30, 40, 50, 60],
            "contaminated_num": ["10", "20", "corrupt_val", "40", "50", "error_str"],
            "legit_text": [
                "Finance",
                "Healthcare",
                "Construction",
                "ICT",
                "Manufacturing",
                "Trade",
            ],
        }
    )

    result = validator.validate(df)
    assert result.passed is True

    # contaminated_num should trigger string contamination warning
    contam_warnings = [w for w in result.warnings if "contaminated_num" in w]
    assert len(contam_warnings) >= 1
    assert "string contamination" in contam_warnings[0]

    # legit_text and clean_numeric should NOT trigger string contamination warnings
    assert not any("legit_text" in w for w in result.warnings)
    assert not any("clean_numeric" in w for w in result.warnings)


def test_validate_date_range_sanity(validator: DataQualityValidator) -> None:
    """Test date range sanity check for years outside 1990–2030."""
    # Valid date range
    df_valid = pd.DataFrame(
        {
            "record_date": pd.date_range("2019-01-01", periods=5, freq="YS"),
            "year": [2019, 2020, 2021, 2022, 2023],
            "value": [100, 105, 110, 115, 120],
        }
    )
    res_valid = validator.validate(df_valid)
    assert not any("1990" in w for w in res_valid.warnings)

    # Historical date before 1990
    df_old = pd.DataFrame(
        {
            "record_date": [datetime(1985, 5, 1, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC)],
            "value": [10, 20],
        }
    )
    res_old = validator.validate(df_old)
    old_warnings = [w for w in res_old.warnings if "record_date" in w]
    assert len(old_warnings) >= 1
    assert "1990" in old_warnings[0]

    # Future date beyond 2030
    df_future = pd.DataFrame(
        {
            "year": [2020, 2025, 2035],
            "value": [50, 60, 70],
        }
    )
    res_future = validator.validate(df_future)
    future_warnings = [w for w in res_future.warnings if "year" in w]
    assert len(future_warnings) >= 1
    assert "2030" in future_warnings[0]


def test_validate_outlier_detection_iqr(validator: DataQualityValidator) -> None:
    """Test statistical outlier detection (> 3 IQR from median)."""
    # Distribution with clear outlier (> 3 IQR)
    # Q1 ~ 10, Q3 ~ 12, IQR ~ 2, Median ~ 11. Upper bound = 11 + 3*2 = 17. 1000 is an outlier.
    df_outliers = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, 6, 7],
            "year": [2020, 2021, 2022, 2023, 2024, 2025, 2026],
            "metric": [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 1000.0],
        }
    )

    result = validator.validate(df_outliers)
    assert result.passed is True

    # metric column should be flagged for outlier
    metric_warnings = [w for w in result.warnings if "metric" in w and "outlier" in w]
    assert len(metric_warnings) == 1
    assert "statistical outlier" in metric_warnings[0]

    # 'id' and 'year' columns must NOT be flagged as outliers
    assert not any("Column 'id'" in w for w in result.warnings)
    assert not any("Column 'year'" in w for w in result.warnings)


def test_validate_non_destructive_and_flag_dataframe(
    validator: DataQualityValidator,
) -> None:
    """Test validation is non-destructive and flag_dataframe attaches _dq_flag column."""
    original_data = {
        "sector": ["ICT", "Finance", "Healthcare", "Manufacturing"],
        "rate": [5.0, 5.2, np.nan, 5.1],  # 25% missing
        "score": [10.0, 10.2, 10.1, 500.0],  # 500 is outlier
    }
    df = pd.DataFrame(original_data)
    orig_rows, orig_cols = df.shape

    # 1. validate() does not mutate original DataFrame
    result = validator.validate(df)
    assert len(df) == orig_rows
    assert len(df.columns) == orig_cols
    assert "_dq_flag" not in df.columns
    assert len(result.warnings) >= 2

    # 2. flag_dataframe() returns copy with _dq_flag without dropping any rows
    flagged_df = validator.flag_dataframe(df)
    assert len(flagged_df) == orig_rows
    assert len(flagged_df.columns) == orig_cols + 1
    assert "_dq_flag" in flagged_df.columns

    # Row 2 (null in rate) and Row 3 (outlier in score) should have _dq_flag=True
    assert flagged_df.loc[2, "_dq_flag"] == np.bool_(True)
    assert flagged_df.loc[3, "_dq_flag"] == np.bool_(True)
    assert flagged_df.loc[0, "_dq_flag"] == np.bool_(False)


def test_validate_non_raising_robustness(validator: DataQualityValidator) -> None:
    """Test validator never raises exceptions even on strange or malformed objects."""
    # DataFrame with complex non-standard objects
    df = pd.DataFrame(
        {
            "weird": [{"a": 1}, lambda x: x, object()],
        }
    )
    result = validator.validate(df)
    assert isinstance(result, ValidationResult)
    assert result.stats["row_count"] == 3


# ---------------------------------------------------------------------------
# 3. DataService Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_service_fetch_and_validate_success() -> None:
    """Test fetch_and_validate fetches data and runs validation smoothly."""
    # Ensure sources registered
    import app.data_sources  # noqa: F401

    service = DataService()
    df, result = await service.fetch_and_validate(
        source_id="mock_internal",
        dataset_id="employment_by_sector_2019_2024",
    )

    assert not df.empty
    assert len(df) > 0
    assert result.passed is True
    assert "data_quality" in df.attrs
    assert result.stats["row_count"] == len(df)
    assert result.stats["col_count"] == len(df.columns)


@pytest.mark.asyncio
async def test_data_service_fetch_and_validate_unregistered_source() -> None:
    """Test fetch_and_validate gracefully returns failed result for unknown source."""
    service = DataService()
    df, result = await service.fetch_and_validate(
        source_id="non_existent_source_12345",
        dataset_id="some_table",
    )

    assert df.empty
    assert result.passed is False
    assert len(result.errors) > 0
    assert "not registered" in result.errors[0]


@pytest.mark.asyncio
async def test_data_service_cache_dataset(async_db: AsyncSession) -> None:
    """Test cache_dataset calculates SHA256 hash and persists into PostgreSQL/SQLite."""
    service = DataService()
    df = pd.DataFrame(
        {
            "sector": ["Technology", "Finance"],
            "year": [2023, 2023],
            "employment": [150000, 240000],
        }
    )

    expected_hash = hashlib.sha256(df.to_json().encode("utf-8")).hexdigest()

    # 1. First cache call creates record
    dataset1 = await service.cache_dataset(
        db=async_db,
        df=df,
        source="singstat_mcp",
        source_id="table_tech_finance",
        metadata={"title": "Tech and Finance Employment"},
    )

    assert isinstance(dataset1, Dataset)
    assert dataset1.data_hash == expected_hash
    assert dataset1.row_count == 2
    assert dataset1.source == "singstat_mcp"
    assert dataset1.title == "Tech and Finance Employment"

    # 2. Second cache call with identical data deduplicates
    dataset2 = await service.cache_dataset(
        db=async_db,
        df=df,
        source="singstat_mcp",
        source_id="table_tech_finance",
    )

    assert dataset2.id == dataset1.id
    assert dataset2.data_hash == expected_hash


def test_data_service_attach_quality_to_metadata() -> None:
    """Test attaching quality warnings and reports to analysis metadata."""
    validation_res = ValidationResult(
        passed=True,
        warnings=["Column 'wages' has 15.0% missing values"],
        errors=[],
        stats={"row_count": 50, "col_count": 4},
    )

    initial_meta = {"sector": "Technology", "data_quality_issues": ["Initial note"]}
    updated_meta = DataService.attach_quality_to_metadata(initial_meta, validation_res)

    assert "data_quality_issues" in updated_meta
    assert "Initial note" in updated_meta["data_quality_issues"]
    assert "Column 'wages' has 15.0% missing values" in updated_meta["data_quality_issues"]
    assert "data_quality_report" in updated_meta
    assert updated_meta["data_quality_report"]["passed"] is True


def test_global_service_singleton_available() -> None:
    """Test global data_service instance is initialized and accessible."""
    assert data_service is not None
    assert isinstance(data_service, DataService)
    assert isinstance(data_service.validator, DataQualityValidator)


# ---------------------------------------------------------------------------
# S29 Specific Acceptance Criteria Checks
# ---------------------------------------------------------------------------


def test_empty_dataframe_fails_passed_false(validator: DataQualityValidator) -> None:
    """Empty DataFrame results in passed=False with explicit error."""
    df_empty = pd.DataFrame()
    result = validator.validate(df_empty)

    assert result.passed is False
    assert len(result.errors) > 0
    assert any("empty" in err.lower() for err in result.errors)


def test_fifty_percent_nulls_generates_warning(validator: DataQualityValidator) -> None:
    """DataFrame with 50% null values in a column generates a quality warning."""
    df_nulls = pd.DataFrame(
        {
            "timestamp": [2020, 2021, 2022, 2023],
            "metric": [10.0, np.nan, 30.0, np.nan],  # Exactly 50% nulls
        }
    )
    result = validator.validate(df_nulls)

    assert result.passed is True  # Non-destructive
    assert len(result.warnings) > 0
    warning_texts = " ".join(result.warnings)
    assert "metric" in warning_texts
    assert "50.0%" in warning_texts
    assert result.stats["null_pct_by_col"]["metric"] == 0.5


def test_outlier_thousand_x_median_generates_warning(validator: DataQualityValidator) -> None:
    """DataFrame with an outlier value 1000x the median generates an outlier warning."""
    # Median is ~10.0, outlier is 10,000.0 (1000x median)
    df_outlier = pd.DataFrame(
        {
            "year": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
            "value": [9.8, 10.0, 10.1, 10.2, 9.9, 10.0, 10000.0],
        }
    )
    result = validator.validate(df_outlier)

    assert result.passed is True
    outlier_warnings = [w for w in result.warnings if "outlier" in w.lower()]
    assert len(outlier_warnings) >= 1
    assert "value" in outlier_warnings[0]
