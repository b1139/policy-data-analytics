"""Abstract data source interface for government data connectors.

Defines the contract matching LLD.md §6 and provides DataFrame normalization
utilities and safe execution patterns.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Standard timeout for health checks across all data source connectors
DEFAULT_HEALTH_CHECK_TIMEOUT: float = 5.0


class AbstractDataSource(ABC):
    """Abstract base class for all policy data source connectors.

    All implementations (SingStat MCP, SingStat REST, Data.gov.sg, Mock DB)
    must implement search, fetch, and health_check according to this contract.
    """

    source_id: str
    display_name: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce presence of class attributes on concrete subclasses."""
        super().__init_subclass__(**kwargs)
        # Only check concrete subclasses (not intermediary ABCs)
        if not getattr(cls, "__abstractmethods__", None):
            if not hasattr(cls, "source_id") or not cls.source_id:
                raise TypeError(
                    f"Class {cls.__name__} must define a non-empty 'source_id' attribute."
                )
            if not hasattr(cls, "display_name") or not cls.display_name:
                raise TypeError(
                    f"Class {cls.__name__} must define a non-empty 'display_name' attribute."
                )

    @classmethod
    def clean_column_name(cls, col: Any) -> str:
        """Normalize a single column name.

        - Strip leading/trailing whitespace
        - Convert to lowercase
        - Replace spaces, dashes, dots, and slashes with underscores
        - Strip non-alphanumeric/non-underscore characters
        - Collapse multiple consecutive underscores
        """
        s = str(col).strip().lower()
        s = re.sub(r"[\s\-\.\/]+", "_", s)
        s = re.sub(r"[^\w_]", "", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("_")

    @classmethod
    def normalize_dataframe(
        cls,
        df: pd.DataFrame,
        metadata: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Normalize a DataFrame to platform standards.

        Standards:
        1. Column names: lowercase, stripped whitespace, underscores instead of spaces/symbols.
        2. Datetime columns: localized or converted to UTC timestamps.
        3. String columns matching date patterns: parsed to UTC timestamps where appropriate.
        4. Metadata: attached to `df.attrs` (source, dataset_id, fetched_at, etc.).

        Args:
            df: Raw pandas DataFrame.
            metadata: Optional dictionary of metadata to attach to `df.attrs`.

        Returns:
            Normalized pandas DataFrame.
        """
        if df is None:
            df = pd.DataFrame()

        if df.empty:
            result_df = df.copy()
            if metadata:
                result_df.attrs.update(metadata)
            return result_df

        result_df = df.copy()

        # 1. Clean column names
        result_df.columns = [cls.clean_column_name(c) for c in result_df.columns]

        # 2. Normalize datetime columns to UTC
        for col in result_df.columns:
            series = result_df[col]
            if pd.api.types.is_datetime64_any_dtype(series):
                if series.dt.tz is None:
                    result_df[col] = series.dt.tz_localize("UTC")
                else:
                    result_df[col] = series.dt.tz_convert("UTC")
            elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                # Check for date-like column names or date strings
                col_lower = str(col).lower()
                is_date_col = any(
                    k in col_lower
                    for k in ("date", "timestamp", "datetime", "period_start", "period_end")
                )
                if is_date_col:
                    try:
                        parsed = pd.to_datetime(series, errors="coerce", utc=True)
                        # Apply only if at least one value was successfully parsed and column wasn't entirely null
                        if not series.isna().all() and not parsed.isna().all():
                            result_df[col] = parsed
                    except Exception as err:
                        logger.debug("Could not parse column '%s' as UTC datetime: %s", col, err)

        # 3. Attach metadata
        default_meta: dict[str, Any] = {
            "source": getattr(cls, "source_id", "unknown"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        if metadata:
            default_meta.update(metadata)
        result_df.attrs.update(default_meta)

        return result_df

    @abstractmethod
    async def search(
        self,
        keywords: str | list[str],
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Search available datasets matching keywords and filters.

        Args:
            keywords: Search keywords as a string or list of strings.
            **filters: Optional filters (e.g. industry, frequency, start_year, end_year).

        Returns:
            List of matching datasets with schema:
            [{
                "id": str,
                "title": str,
                "description": str,
                "url": str,
                "format": str
            }]
        """
        pass

    @abstractmethod
    async def fetch(self, dataset_id: str) -> pd.DataFrame:
        """Fetch and return a normalized pandas DataFrame for the given dataset ID.

        Contract Requirements:
        - Must return a normalized DataFrame (lowercase cols, UTC dates).
        - Must attach source metadata to `df.attrs`.
        - MUST NEVER RAISE an unhandled exception on failure; catch errors,
          log warnings, and return an empty `pd.DataFrame()`.

        Args:
            dataset_id: Unique identifier for the dataset in this source.

        Returns:
            pd.DataFrame: Normalized dataset, or empty DataFrame on failure.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check source availability with a maximum 5-second timeout.

        Returns:
            bool: True if source is healthy/responsive, False otherwise.
        """
        pass

    async def safe_health_check(self, timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT) -> bool:
        """Execute health_check wrapped in a hard timeout and exception catcher.

        Args:
            timeout: Maximum wait time in seconds (default: 5.0s).

        Returns:
            bool: True if healthy within timeout, False otherwise.
        """
        try:
            return await asyncio.wait_for(self.health_check(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                "Health check timed out after %.1fs for data source '%s'",
                timeout,
                getattr(self, "source_id", "unknown"),
            )
            return False
        except Exception as exc:
            logger.warning(
                "Health check failed with error for data source '%s': %s",
                getattr(self, "source_id", "unknown"),
                exc,
            )
            return False
