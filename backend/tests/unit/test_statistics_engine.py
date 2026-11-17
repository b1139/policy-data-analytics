"""Unit tests for the StatisticsEngine and statistical analytics schemas."""

import numpy as np
import pandas as pd
import pytest

from app.schemas.analytics import (
    CorrelationResult,
    SectorShareResult,
    StatsResult,
    SummaryResult,
    TrendResult,
)
from app.services.analysis_service import StatisticsEngine


class TestStatisticsEngineTrend:
    """Tests for StatisticsEngine.compute_trend linear regression and YoY growth."""

    def test_compute_trend_increasing(self):
        """Test linear increasing trend produces positive slope and 'increasing' classification."""
        df = pd.DataFrame(
            {
                "year": [2018, 2019, 2020, 2021, 2022],
                "cpi": [100.0, 102.5, 105.0, 108.0, 111.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="cpi", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.error is None
        assert res.slope is not None and res.slope > 0
        assert res.r2 is not None and res.r2 > 0.98
        assert res.p_value is not None and res.p_value < 0.05
        assert res.overall_trend == "increasing"

        # Check YoY growth
        assert "2019" in res.yoy_growth
        assert res.yoy_growth["2019"] == pytest.approx(2.5, abs=0.01)
        assert "2020" in res.yoy_growth
        assert res.yoy_growth["2020"] == pytest.approx(2.44, abs=0.01)

    def test_compute_trend_decreasing(self):
        """Test linear decreasing trend produces negative slope and 'decreasing' classification."""
        df = pd.DataFrame(
            {
                "year": [2018, 2019, 2020, 2021, 2022],
                "unemployment_rate": [3.5, 3.2, 2.9, 2.6, 2.3],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="unemployment_rate", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.error is None
        assert res.slope is not None and res.slope < 0
        assert res.p_value is not None and res.p_value < 0.05
        assert res.overall_trend == "decreasing"
        assert res.yoy_growth["2019"] < 0

    def test_compute_trend_stable_or_noisy(self):
        """Test noisy or flat series produces 'stable' overall_trend."""
        df = pd.DataFrame(
            {
                "year": [2018, 2019, 2020, 2021, 2022],
                "val": [10.0, 10.1, 9.9, 10.0, 10.05],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.error is None
        # With very small variation, p-value is large (>0.05), so overall trend is stable
        assert res.overall_trend == "stable"

    def test_compute_trend_with_nans(self):
        """Test NaN values are dropped cleanly before trend regression."""
        df = pd.DataFrame(
            {
                "year": [2018, None, 2020, 2021, 2022],
                "val": [10.0, 12.0, np.nan, 16.0, 19.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="year")

        assert isinstance(res, TrendResult)
        # 3 valid points remain (2018, 2021, 2022)
        assert res.error is None
        assert res.slope is not None and res.slope > 0
        assert res.overall_trend in ["increasing", "stable"]

    def test_compute_trend_insufficient_data(self):
        """Test < 3 valid observations returns error without crashing."""
        df = pd.DataFrame(
            {
                "year": [2020, 2021],
                "val": [10.0, 15.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.error == "insufficient_data"
        assert res.overall_trend == "stable"
        assert res.slope is None

    def test_compute_trend_constant_values(self):
        """Test constant values (zero variance) handle gracefully."""
        df = pd.DataFrame(
            {
                "year": [2019, 2020, 2021, 2022],
                "val": [5.0, 5.0, 5.0, 5.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.error is None
        assert res.slope == 0.0
        assert res.overall_trend == "stable"
        for growth in res.yoy_growth.values():
            assert growth == 0.0

    def test_compute_trend_zero_previous_value_yoy(self):
        """Test YoY percentage change handles zero in previous period without ZeroDivisionError."""
        df = pd.DataFrame(
            {
                "year": [2020, 2021, 2022],
                "val": [0.0, 50.0, 75.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="year")

        assert isinstance(res, TrendResult)
        assert res.yoy_growth["2021"] == 0.0
        assert res.yoy_growth["2022"] == pytest.approx(50.0)

    def test_compute_trend_datetime_strings(self):
        """Test trend computation with ISO-formatted date strings."""
        df = pd.DataFrame(
            {
                "date": ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"],
                "val": [10.0, 20.0, 30.0, 40.0],
            }
        )
        res = StatisticsEngine.compute_trend(df, value_col="val", time_col="date")

        assert isinstance(res, TrendResult)
        assert res.slope is not None and res.slope > 0
        assert res.overall_trend == "increasing"


class TestStatisticsEngineSummary:
    """Tests for StatisticsEngine.compute_summary_stats."""

    def test_compute_summary_stats_valid(self):
        """Test accurate computation of descriptive statistics."""
        df = pd.DataFrame(
            {
                "val": [10.0, 20.0, 30.0, 40.0, 50.0],
            }
        )
        res = StatisticsEngine.compute_summary_stats(df, value_col="val")

        assert isinstance(res, SummaryResult)
        assert res.count == 5
        assert res.mean == pytest.approx(30.0)
        assert res.median == pytest.approx(30.0)
        assert res.min == pytest.approx(10.0)
        assert res.max == pytest.approx(50.0)
        assert res.earliest_value == pytest.approx(10.0)
        assert res.latest_value == pytest.approx(50.0)
        assert res.std == pytest.approx(15.8114, abs=0.01)
        assert res.error is None

    def test_compute_summary_stats_with_nans_and_strings(self):
        """Test non-numeric values and NaNs are safely filtered."""
        df = pd.DataFrame(
            {
                "val": ["10", None, "invalid", 20.0, np.nan, 30.0],
            }
        )
        res = StatisticsEngine.compute_summary_stats(df, value_col="val")

        assert res.count == 3
        assert res.mean == pytest.approx(20.0)
        assert res.min == pytest.approx(10.0)
        assert res.max == pytest.approx(30.0)

    def test_compute_summary_stats_empty_or_missing(self):
        """Test empty series or missing column returns insufficient_data."""
        df_empty = pd.DataFrame({"val": []})
        res = StatisticsEngine.compute_summary_stats(df_empty, value_col="val")
        assert res.count == 0
        assert res.error == "insufficient_data"

        res_missing = StatisticsEngine.compute_summary_stats(df_empty, value_col="non_existent")
        assert res_missing.count == 0
        assert res_missing.error == "insufficient_data"


class TestStatisticsEngineSectorShare:
    """Tests for StatisticsEngine.compute_sector_share."""

    def test_compute_sector_share_all(self):
        """Test sector breakdown percentages sum to 100%."""
        df = pd.DataFrame(
            {
                "sector": ["Finance", "Technology", "Manufacturing", "Retail"],
                "value": [400.0, 300.0, 200.0, 100.0],
            }
        )
        res = StatisticsEngine.compute_sector_share(df, sector_col="sector", value_col="value")

        assert isinstance(res, SectorShareResult)
        assert res.error is None
        assert res.shares["Finance"] == pytest.approx(40.0)
        assert res.shares["Technology"] == pytest.approx(30.0)
        assert res.shares["Manufacturing"] == pytest.approx(20.0)
        assert res.shares["Retail"] == pytest.approx(10.0)
        assert sum(res.shares.values()) == pytest.approx(100.0, abs=0.1)

    def test_compute_sector_share_filtered_by_year(self):
        """Test sector share when filtered by year column."""
        df = pd.DataFrame(
            {
                "year": [2021, 2021, 2022, 2022],
                "sector": ["Tech", "Finance", "Tech", "Finance"],
                "jobs": [100.0, 100.0, 300.0, 100.0],
            }
        )
        res = StatisticsEngine.compute_sector_share(
            df,
            sector_col="sector",
            value_col="jobs",
            year=2022,
        )

        assert res.year == 2022
        assert res.shares["Tech"] == pytest.approx(75.0)
        assert res.shares["Finance"] == pytest.approx(25.0)

    def test_compute_sector_share_empty(self):
        """Test empty dataframe returns insufficient_data."""
        df = pd.DataFrame(columns=["sector", "value"])
        res = StatisticsEngine.compute_sector_share(df, sector_col="sector", value_col="value")
        assert res.error == "insufficient_data"
        assert res.shares == {}

    def test_compute_sector_share_all_zeros(self):
        """Test sector share when total sum is 0.0."""
        df = pd.DataFrame(
            {
                "sector": ["A", "B"],
                "value": [0.0, 0.0],
            }
        )
        res = StatisticsEngine.compute_sector_share(df, sector_col="sector", value_col="value")
        assert res.shares["A"] == 0.0
        assert res.shares["B"] == 0.0


class TestStatisticsEngineCorrelation:
    """Tests for StatisticsEngine.compute_correlation."""

    def test_compute_correlation_strong_positive(self):
        """Test strong positive correlation calculation and interpretation."""
        df = pd.DataFrame(
            {
                "education_years": [10, 12, 14, 16, 18, 20],
                "income": [3000, 3800, 4800, 6200, 7800, 9500],
            }
        )
        res = StatisticsEngine.compute_correlation(df, "education_years", "income")

        assert isinstance(res, CorrelationResult)
        assert res.error is None
        assert res.pearson_r is not None and res.pearson_r > 0.95
        assert res.spearman_r is not None and res.spearman_r > 0.95
        assert res.p_value is not None and res.p_value < 0.01
        assert "Strong positive correlation" in res.interpretation
        assert "statistically significant" in res.interpretation

    def test_compute_correlation_negative(self):
        """Test negative correlation calculation and interpretation."""
        df = pd.DataFrame(
            {
                "inflation": [1.0, 2.5, 4.0, 5.5, 7.0],
                "purchasing_power": [100, 92, 85, 76, 68],
            }
        )
        res = StatisticsEngine.compute_correlation(df, "inflation", "purchasing_power")

        assert res.pearson_r is not None and res.pearson_r < -0.9
        assert "negative" in res.interpretation

    def test_compute_correlation_insufficient_data(self):
        """Test fewer than 3 pairs returns insufficient_data error."""
        df = pd.DataFrame(
            {
                "a": [1.0, 2.0],
                "b": [3.0, 4.0],
            }
        )
        res = StatisticsEngine.compute_correlation(df, "a", "b")
        assert res.error == "insufficient_data"
        assert res.pearson_r is None

    def test_compute_correlation_constant_column(self):
        """Test column with zero variance returns clean result."""
        df = pd.DataFrame(
            {
                "a": [5.0, 5.0, 5.0, 5.0],
                "b": [1.0, 2.0, 3.0, 4.0],
            }
        )
        res = StatisticsEngine.compute_correlation(df, "a", "b")
        assert res.pearson_r == 0.0
        assert "No variation" in res.interpretation

    def test_compute_correlation_with_nans_and_strings(self):
        """Test correlation computation handles missing data and string coercion."""
        df = pd.DataFrame(
            {
                "a": ["1.0", "2.0", np.nan, "4.0", "5.0"],
                "b": [2.0, np.nan, 3.0, 8.0, 10.0],
            }
        )
        res = StatisticsEngine.compute_correlation(df, "a", "b")
        # Valid pairs: index 0 (1,2), index 3 (4,8), index 4 (5,10) -> exactly 3 points
        assert res.error is None
        assert res.pearson_r is not None and res.pearson_r > 0.99


class TestStatisticsEngineConsolidated:
    """Tests for StatisticsEngine.compute_statistics aggregating all components."""

    def test_compute_statistics_full(self):
        """Test full compute_statistics execution returns typed StatsResult."""
        df = pd.DataFrame(
            {
                "year": [2020, 2021, 2022, 2023],
                "sector": ["Tech", "Finance", "Tech", "Finance"],
                "value": [100.0, 110.0, 125.0, 140.0],
                "secondary": [50.0, 55.0, 62.0, 70.0],
            }
        )

        stats_res = StatisticsEngine.compute_statistics(
            df=df,
            value_col="value",
            time_col="year",
            sector_col="sector",
            secondary_val_col="secondary",
            metadata={"source": "singstat_mock"},
        )

        assert isinstance(stats_res, StatsResult)
        assert stats_res.summary is not None
        assert stats_res.summary.count == 4
        assert stats_res.trend is not None
        assert stats_res.trend.overall_trend == "increasing"
        assert stats_res.sector_shares is not None
        assert len(stats_res.correlations) == 1
        assert stats_res.correlations[0].pearson_r is not None
        assert stats_res.metadata["source"] == "singstat_mock"

    def test_stats_result_single_correlation_normalization(self):
        """Test StatsResult wraps a single correlation object or None into a list."""
        corr = CorrelationResult(
            pearson_r=0.8,
            spearman_r=0.75,
            p_value=0.01,
            interpretation="Strong correlation",
        )
        res = StatsResult(correlations=corr)
        assert len(res.correlations) == 1
        assert res.correlations[0].pearson_r == 0.8

        res_none = StatsResult(correlations=None)
        assert res_none.correlations == []
