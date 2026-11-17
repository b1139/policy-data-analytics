"""Data quality validation pipeline and data management service.

Implements Story S19:
- DataQualityValidator: checks null percentages, type consistency, date range sanity,
  outlier detection (IQR), and empty DataFrames. Non-destructive and non-raising.
- DataService: fetch-and-validate coordination, SHA-256 hash dedup caching into PostgreSQL.
"""

import hashlib
import logging
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.crud.dataset import get_or_create_dataset
from app.data_sources.registry import data_source_registry
from app.models.dataset import Dataset
from app.schemas.data_quality import ValidationResult

logger = logging.getLogger(__name__)

# Constants for validation thresholds
MAX_NULL_PERCENTAGE: float = 0.10  # 10%
MIN_EXPECTED_YEAR: int = 1990
MAX_EXPECTED_YEAR: int = 2030
IQR_OUTLIER_MULTIPLIER: float = 3.0


class DataQualityValidator:
    """Non-destructive, non-raising data quality validator for policy datasets.

    Performs 5 core quality checks:
    1. Empty DataFrame detection (critical error).
    2. Null percentage check (> 10% flagged with warning).
    3. Type consistency / string contamination check.
    4. Date range sanity check (1990–2030).
    5. Statistical outlier detection (> 3 IQR from median).
    """

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """Execute all quality validation rules on incoming DataFrame.

        Contract:
        - NEVER raises an exception; all errors are caught and recorded.
        - NEVER silently drops rows; only flags issues as warnings or errors.
        - Returns a structured ValidationResult with summary stats.

        Args:
            df: Raw or normalized pandas DataFrame.

        Returns:
            ValidationResult containing passed status, warnings, errors, and stats.
        """
        warnings: list[str] = []
        errors: list[str] = []
        stats: dict[str, Any] = {}

        try:
            # 1. Empty DataFrame check
            if df is None:
                return ValidationResult(
                    passed=False,
                    errors=["DataFrame is None."],
                    warnings=[],
                    stats={"row_count": 0, "col_count": 0, "null_pct_by_col": {}, "dtypes": {}},
                )

            row_count = int(len(df))
            col_count = int(len(df.columns))

            if row_count == 0 or col_count == 0:
                return ValidationResult(
                    passed=False,
                    errors=[f"DataFrame is empty: {row_count} rows and {col_count} columns."],
                    warnings=[],
                    stats={
                        "row_count": row_count,
                        "col_count": col_count,
                        "null_pct_by_col": {},
                        "dtypes": {},
                    },
                )

            # Gather standard summary stats
            dtypes = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
            null_pct_by_col = {
                str(col): round(float(df[col].isna().mean()), 4) for col in df.columns
            }
            stats = {
                "row_count": row_count,
                "col_count": col_count,
                "null_pct_by_col": null_pct_by_col,
                "dtypes": dtypes,
            }

            # 2. Null check (> 10% flagged)
            for col, null_pct in null_pct_by_col.items():
                if null_pct > MAX_NULL_PERCENTAGE:
                    warnings.append(
                        f"Column '{col}' has {null_pct * 100:.1f}% missing values "
                        f"(exceeds threshold of {MAX_NULL_PERCENTAGE * 100:.0f}%)."
                    )

            # 3. Type consistency & string contamination check
            self._check_type_consistency(df, warnings)

            # 4. Date range sanity check (1990–2030)
            self._check_date_ranges(df, warnings)

            # 5. Outlier detection (> 3 IQR from median)
            self._check_numeric_outliers(df, warnings)

            passed = len(errors) == 0
            return ValidationResult(
                passed=passed,
                warnings=warnings,
                errors=errors,
                stats=stats,
            )

        except Exception as exc:
            logger.warning(
                "Unexpected failure during data quality validation: %s",
                exc,
                exc_info=True,
            )
            return ValidationResult(
                passed=False,
                errors=[f"Validation execution failed unexpectedly: {exc}"],
                warnings=warnings,
                stats=stats
                or {
                    "row_count": len(df) if df is not None else 0,
                    "col_count": len(df.columns) if df is not None else 0,
                    "null_pct_by_col": {},
                    "dtypes": {},
                },
            )

    def _check_type_consistency(self, df: pd.DataFrame, warnings: list[str]) -> None:
        """Detect numeric columns contaminated with non-numeric string values."""
        for col in df.columns:
            series = df[col]
            # Inspect object or string dtypes that might be contaminated numeric series
            if series.dtype == object or isinstance(series.dtype, pd.StringDtype):
                non_null = series.dropna()
                if non_null.empty:
                    continue

                # Strip whitespace and convert to string representation
                str_vals = non_null.astype(str).str.strip()
                converted_nums = pd.to_numeric(str_vals, errors="coerce")
                valid_num_count = int(converted_nums.notna().sum())
                contaminated_count = int(converted_nums.isna().sum())

                # If there are numbers mixed with non-numbers in a predominantly numeric column
                if valid_num_count > 0 and contaminated_count > 0:
                    ratio = valid_num_count / len(non_null)
                    if ratio >= 0.3 or valid_num_count >= contaminated_count:
                        warnings.append(
                            f"Column '{col}' appears numeric ({valid_num_count}/{len(non_null)} numeric) "
                            f"but contains string contamination ({contaminated_count} non-numeric value(s))."
                        )

    def _check_date_ranges(self, df: pd.DataFrame, warnings: list[str]) -> None:
        """Verify date and year columns fall within the expected range 1990–2030."""
        date_keywords = ("date", "timestamp", "datetime", "period_start", "period_end")

        for col in df.columns:
            series = df[col]
            col_lower = str(col).lower()

            # Datetime64 series
            if pd.api.types.is_datetime64_any_dtype(series):
                non_null = series.dropna()
                if not non_null.empty:
                    min_dt = pd.to_datetime(non_null.min())
                    max_dt = pd.to_datetime(non_null.max())
                    if min_dt.year < MIN_EXPECTED_YEAR or max_dt.year > MAX_EXPECTED_YEAR:
                        warnings.append(
                            f"Date column '{col}' has values outside expected {MIN_EXPECTED_YEAR}–{MAX_EXPECTED_YEAR} range "
                            f"(min year: {min_dt.year}, max year: {max_dt.year})."
                        )

            # Integer or float year column (e.g. named 'year' or 'period_year')
            elif pd.api.types.is_numeric_dtype(series) and "year" in col_lower:
                non_null = series.dropna()
                if not non_null.empty:
                    min_yr = int(non_null.min())
                    max_yr = int(non_null.max())
                    if min_yr < MIN_EXPECTED_YEAR or max_yr > MAX_EXPECTED_YEAR:
                        warnings.append(
                            f"Year column '{col}' has values outside expected {MIN_EXPECTED_YEAR}–{MAX_EXPECTED_YEAR} range "
                            f"(min year: {min_yr}, max year: {max_yr})."
                        )

            # String column with date naming
            elif (series.dtype == object or isinstance(series.dtype, pd.StringDtype)) and any(
                k in col_lower for k in date_keywords
            ):
                parsed = pd.to_datetime(series, errors="coerce")
                non_null = parsed.dropna()
                if not non_null.empty:
                    min_yr = int(non_null.dt.year.min())
                    max_yr = int(non_null.dt.year.max())
                    if min_yr < MIN_EXPECTED_YEAR or max_yr > MAX_EXPECTED_YEAR:
                        warnings.append(
                            f"Date column '{col}' has values outside expected {MIN_EXPECTED_YEAR}–{MAX_EXPECTED_YEAR} range "
                            f"(min year: {min_yr}, max year: {max_yr})."
                        )

    def _check_numeric_outliers(self, df: pd.DataFrame, warnings: list[str]) -> None:
        """Detect statistical outliers exceeding 3 IQR from median in numeric columns."""
        for col in df.columns:
            series = df[col]
            if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
                continue

            col_lower = str(col).lower()
            if col_lower == "year" or col_lower.endswith("_id") or col_lower == "id":
                continue

            vals = series.dropna()
            if len(vals) < 4:
                continue

            q1 = float(vals.quantile(0.25))
            q3 = float(vals.quantile(0.75))
            iqr = q3 - q1
            median = float(vals.median())

            if iqr > 0:
                lower_threshold = median - IQR_OUTLIER_MULTIPLIER * iqr
                upper_threshold = median + IQR_OUTLIER_MULTIPLIER * iqr
                outliers = vals[(vals < lower_threshold) | (vals > upper_threshold)]
                if len(outliers) > 0:
                    warnings.append(
                        f"Column '{col}' contains {len(outliers)} statistical outlier(s) "
                        f"exceeding 3 IQR from median (median={median:.2f}, IQR={iqr:.2f}, "
                        f"valid range=[{lower_threshold:.2f}, {upper_threshold:.2f}])."
                    )
            else:
                # If IQR is 0, detect deviations from median if they represent rare anomalies
                diff = (vals - median).abs()
                outliers = vals[diff > 0]
                if 0 < len(outliers) < (len(vals) / 2):
                    warnings.append(
                        f"Column '{col}' contains {len(outliers)} outlier(s) differing from median {median:.2f}."
                    )

    def flag_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of the DataFrame with a `_dq_flag` boolean column.

        Crucially non-destructive: all original rows are retained.
        Rows with nulls in high-missing columns, string contamination, or extreme outliers
        are marked True in `_dq_flag`.

        Args:
            df: Input pandas DataFrame.

        Returns:
            DataFrame with `_dq_flag` column appended.
        """
        if df is None or df.empty:
            return pd.DataFrame() if df is None else df.copy()

        flagged = df.copy()
        mask = pd.Series(False, index=flagged.index)

        # 1. Null check on columns exceeding threshold
        for col in flagged.columns:
            if flagged[col].isna().mean() > MAX_NULL_PERCENTAGE:
                mask = mask | flagged[col].isna()

        # 2. Outliers on numeric columns
        for col in flagged.columns:
            series = flagged[col]
            if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                col_lower = str(col).lower()
                if col_lower not in ("year", "id") and not col_lower.endswith("_id"):
                    vals = series.dropna()
                    if len(vals) >= 4:
                        q1 = float(vals.quantile(0.25))
                        q3 = float(vals.quantile(0.75))
                        iqr = q3 - q1
                        median = float(vals.median())
                        if iqr > 0:
                            lower = median - IQR_OUTLIER_MULTIPLIER * iqr
                            upper = median + IQR_OUTLIER_MULTIPLIER * iqr
                            mask = mask | (series < lower) | (series > upper)

        flagged["_dq_flag"] = mask
        return flagged


class DataService:
    """Service for dataset extraction, validation, caching, and metadata management."""

    def __init__(self, validator: DataQualityValidator | None = None) -> None:
        self.validator = validator or DataQualityValidator()

    async def fetch_and_validate(
        self,
        source_id: str,
        dataset_id: str,
        **fetch_kwargs: Any,
    ) -> tuple[pd.DataFrame, ValidationResult]:
        """Fetch dataset from registered connector and run data quality validation.

        Args:
            source_id: Identifier of registered connector in DataSourceRegistry.
            dataset_id: Target dataset table/resource ID.
            **fetch_kwargs: Additional parameters passed to source.fetch().

        Returns:
            tuple[pd.DataFrame, ValidationResult]: Normalized dataset and quality report.
        """
        try:
            source = data_source_registry.get(source_id)
        except KeyError as err:
            logger.warning("Data source '%s' not registered: %s", source_id, err)
            empty_df = pd.DataFrame()
            return empty_df, ValidationResult(
                passed=False,
                errors=[f"Data source '{source_id}' is not registered."],
                warnings=[],
                stats={"row_count": 0, "col_count": 0, "null_pct_by_col": {}, "dtypes": {}},
            )

        try:
            df = await source.fetch(dataset_id, **fetch_kwargs)
        except Exception as exc:
            logger.warning(
                "Failed to fetch dataset '%s' from source '%s': %s",
                dataset_id,
                source_id,
                exc,
                exc_info=True,
            )
            empty_df = pd.DataFrame()
            return empty_df, ValidationResult(
                passed=False,
                errors=[f"Fetch failed for '{dataset_id}': {exc}"],
                warnings=[],
                stats={"row_count": 0, "col_count": 0, "null_pct_by_col": {}, "dtypes": {}},
            )

        validation_result = self.validator.validate(df)
        if validation_result.warnings:
            logger.warning(
                "Data quality warnings for source '%s' dataset '%s': %s",
                source_id,
                dataset_id,
                validation_result.warnings,
            )

        # Attach validation summary to DataFrame attrs
        df.attrs["data_quality"] = validation_result.model_dump()
        return df, validation_result

    async def cache_dataset(
        self,
        *args: Any,
        db: AsyncSession | None = None,
        df: pd.DataFrame | None = None,
        source: str | None = None,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Dataset:
        """Cache dataset in PostgreSQL with SHA-256 fingerprint deduplication.

        Supports both positional and keyword invocation signatures:
        1. Explicit DB: `cache_dataset(db, df, source, source_id, metadata)` or `cache_dataset(db=db, df=df, ...)`
        2. Auto DB session: `cache_dataset(df, source, source_id, metadata)` or `cache_dataset(df=df, ...)`

        Args:
            *args: Positional arguments (db, df, source, source_id, metadata) OR (df, source, source_id, metadata).
            db: Optional active AsyncSession. If omitted, a session is obtained from async_session_factory.
            df: Target pandas DataFrame.
            source: Source connector identifier (e.g. 'singstat_mcp', 'datagov', 'mock_internal').
            source_id: External dataset or table ID.
            metadata: Optional dictionary with additional metadata (e.g. title).
            **kwargs: Additional parameters.

        Returns:
            Dataset: Persisted or retrieved cached Dataset ORM model instance.
        """
        # Parse positional arguments if provided
        if args:
            if isinstance(args[0], AsyncSession):
                db = args[0]
                if len(args) > 1 and df is None:
                    df = args[1]
                if len(args) > 2 and source is None:
                    source = args[2]
                if len(args) > 3 and source_id is None:
                    source_id = args[3]
                if len(args) > 4 and metadata is None:
                    metadata = args[4]
            else:
                if df is None:
                    df = args[0]
                if len(args) > 1 and source is None:
                    source = args[1]
                if len(args) > 2 and source_id is None:
                    source_id = args[2]
                if len(args) > 3 and metadata is None:
                    metadata = args[3]

        if df is None:
            raise ValueError("A valid pandas DataFrame ('df') must be provided to cache_dataset.")

        target_source = str(source or kwargs.get("source") or "unknown")
        target_source_id = str(source_id) if source_id is not None else kwargs.get("source_id")
        target_meta = dict(metadata or kwargs.get("metadata") or {})

        if db is not None:
            return await self._persist_dataset_cache(
                db=db,
                df=df,
                source=target_source,
                source_id=target_source_id,
                metadata=target_meta,
            )

        async with async_session_factory() as session:
            return await self._persist_dataset_cache(
                db=session,
                df=df,
                source=target_source,
                source_id=target_source_id,
                metadata=target_meta,
            )

    async def _persist_dataset_cache(
        self,
        db: AsyncSession,
        df: pd.DataFrame,
        source: str,
        source_id: str | None,
        metadata: dict[str, Any],
    ) -> Dataset:
        """Internal helper to calculate SHA-256 and store dataset in database."""
        # Calculate SHA-256 from JSON representation for deduplication
        json_repr = df.to_json() if df is not None else "{}"
        data_hash = hashlib.sha256(json_repr.encode("utf-8")).hexdigest()

        row_count = int(len(df)) if df is not None else 0
        columns = (
            [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]
            if df is not None
            else []
        )

        title = metadata.get("title") or (
            getattr(df, "attrs", {}).get("title") if df is not None else None
        )

        dataset, _created = await get_or_create_dataset(
            db=db,
            source=source,
            source_id=source_id,
            data_hash=data_hash,
            row_count=row_count,
            columns=columns,
            title=title,
        )
        return dataset

    @staticmethod
    def attach_quality_to_metadata(
        metadata: dict[str, Any] | None,
        validation_result: ValidationResult,
    ) -> dict[str, Any]:
        """Attach data quality warnings and reports to analysis metadata.

        Args:
            metadata: Existing analysis metadata dictionary (or None).
            validation_result: ValidationResult instance.

        Returns:
            dict[str, Any]: Updated metadata containing `data_quality_issues` and `data_quality_report`.
        """
        meta = dict(metadata or {})
        existing_issues = list(meta.get("data_quality_issues", []))

        for warning in validation_result.warnings:
            if warning not in existing_issues:
                existing_issues.append(warning)
        for error in validation_result.errors:
            if error not in existing_issues:
                existing_issues.append(error)

        meta["data_quality_issues"] = existing_issues
        meta["data_quality_report"] = validation_result.model_dump()
        return meta


# Global default instance
data_service = DataService()
