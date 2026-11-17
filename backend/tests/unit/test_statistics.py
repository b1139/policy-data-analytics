"""Unit tests for statistical analytics engine and indicators (Story S29).

Verifies:
- compute_trend with monotonically increasing data -> overall_trend="increasing"
- compute_summary_stats produces exact mean, median, min, max, std
- compute_trend with < 3 rows returns error result without crashing
- compute_correlation between two series
- compute_sector_share distribution calculation
"""

import pandas as pd
import pytest

from app.schemas.analytics import CorrelationResult, SectorShareResult, SummaryResult, TrendResult
from app.services.analysis_service import StatisticsEngine


class TestStatistics:
    """Unit test suite for StatisticsEngine functions."""

    def test_compute_trend_monotonically_increasing(self):
        """compute_trend with monotonically increasing data returns overall_trend='increasing'."""
        df = pd.DataFrame(
            {
                "year": [2018, 2019, 2020, 2021, 2022],
                "value": [10.0, 15.0, 20.0, 25.0, 30.0],
            }
        )

        result = StatisticsEngine.compute_trend(df, value_col="value", time_col="year")

        assert isinstance(result, TrendResult)
        assert result.error is None
        assert result.overall_trend == "increasing"
        assert result.slope is not None and result.slope > 0
        assert result.r2 is not None and result.r2 > 0.99
        assert result.p_value is not None and result.p_value < 0.05
        # Verify YoY growth exists
        assert len(result.yoy_growth) == 4
        assert result.yoy_growth["2019"] == pytest.approx(50.0)

    def test_compute_summary_stats_mean_median_values(self):
        """compute_summary_stats returns correct mean, median, min, max, std."""
        df = pd.DataFrame(
            {
                "value": [10.0, 20.0, 30.0, 40.0, 50.0],
            }
        )

        result = StatisticsEngine.compute_summary_stats(df, value_col="value")

        assert isinstance(result, SummaryResult)
        assert result.error is None
        assert result.count == 5
        assert result.mean == pytest.approx(30.0)
        assert result.median == pytest.approx(30.0)
        assert result.min == pytest.approx(10.0)
        assert result.max == pytest.approx(50.0)
        assert result.earliest_value == pytest.approx(10.0)
        assert result.latest_value == pytest.approx(50.0)
        assert result.std == pytest.approx(15.8114, abs=0.01)

    def test_compute_trend_insufficient_rows_no_crash(self):
        """compute_trend with < 3 rows returns error result without crashing."""
        df = pd.DataFrame(
            {
                "year": [2021, 2022],
                "value": [100.0, 110.0],
            }
        )

        result = StatisticsEngine.compute_trend(df, value_col="value", time_col="year")

        assert isinstance(result, TrendResult)
        assert result.error == "insufficient_data"
        assert result.overall_trend == "stable"
        assert result.slope is None
        assert result.r2 is None

    def test_compute_trend_single_row_no_crash(self):
        """compute_trend with 1 row returns error result without crashing."""
        df = pd.DataFrame(
            {
                "year": [2022],
                "value": [100.0],
            }
        )

        result = StatisticsEngine.compute_trend(df, value_col="value", time_col="year")

        assert isinstance(result, TrendResult)
        assert result.error == "insufficient_data"

    def test_compute_correlation_strong_positive(self):
        """compute_correlation accurately computes Pearson r between two variables."""
        df = pd.DataFrame(
            {
                "var1": [1.0, 2.0, 3.0, 4.0, 5.0],
                "var2": [2.0, 4.0, 6.0, 8.0, 10.0],
            }
        )

        result = StatisticsEngine.compute_correlation(df, col_a="var1", col_b="var2")

        assert isinstance(result, CorrelationResult)
        assert result.error is None
        assert result.pearson_r == pytest.approx(1.0)
        assert "positive" in result.interpretation.lower()

    def test_compute_sector_shares(self):
        """compute_sector_share accurately computes percentage distribution."""
        df = pd.DataFrame(
            {
                "sector": ["Tech", "Finance", "Healthcare"],
                "employment": [50.0, 30.0, 20.0],
            }
        )

        result = StatisticsEngine.compute_sector_share(
            df, sector_col="sector", value_col="employment"
        )

        assert isinstance(result, SectorShareResult)
        assert result.error is None
        assert result.shares["Tech"] == pytest.approx(50.0)
        assert result.shares["Finance"] == pytest.approx(30.0)
        assert result.shares["Healthcare"] == pytest.approx(20.0)
