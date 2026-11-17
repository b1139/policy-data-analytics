"""Pydantic schemas for statistical analysis engine results."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrendResult(BaseModel):
    """Result of linear regression trend analysis and YoY growth calculations."""

    slope: float | None = Field(
        default=None,
        description="Slope of the linear trend line",
    )
    intercept: float | None = Field(
        default=None,
        description="Y-intercept of the linear trend line",
    )
    r2: float | None = Field(
        default=None,
        description="Coefficient of determination (R-squared)",
    )
    p_value: float | None = Field(
        default=None,
        description="Two-sided p-value for hypothesis test that slope is zero",
    )
    yoy_growth: dict[str, float] = Field(
        default_factory=dict,
        description="Year-over-year percentage growth rates keyed by year/period string",
    )
    overall_trend: Literal["increasing", "decreasing", "stable"] | str = Field(
        default="stable",
        description="Overall trend direction (increasing, decreasing, or stable)",
    )
    error: str | None = Field(
        default=None,
        description="Error indicator if computation was unable to proceed",
    )

    model_config = ConfigDict(from_attributes=True)


class SummaryResult(BaseModel):
    """Summary statistics for a continuous numerical series."""

    mean: float | None = Field(
        default=None,
        description="Arithmetic mean of values",
    )
    median: float | None = Field(
        default=None,
        description="Median (50th percentile) value",
    )
    std: float | None = Field(
        default=None,
        description="Sample standard deviation (ddof=1)",
    )
    min: float | None = Field(
        default=None,
        description="Minimum value",
    )
    max: float | None = Field(
        default=None,
        description="Maximum value",
    )
    count: int = Field(
        default=0,
        description="Number of valid non-null observations",
    )
    latest_value: float | None = Field(
        default=None,
        description="Latest chronological observation value",
    )
    earliest_value: float | None = Field(
        default=None,
        description="Earliest chronological observation value",
    )
    error: str | None = Field(
        default=None,
        description="Error indicator if computation was unable to proceed",
    )

    model_config = ConfigDict(from_attributes=True)


class SectorShareResult(BaseModel):
    """Sector distribution and market share breakdown."""

    year: int | str | None = Field(
        default=None,
        description="Target evaluation year or time period",
    )
    shares: dict[str, float] = Field(
        default_factory=dict,
        description="Sector percentage shares (summing to ~100%)",
    )
    error: str | None = Field(
        default=None,
        description="Error indicator if computation was unable to proceed",
    )

    model_config = ConfigDict(from_attributes=True)


class CorrelationResult(BaseModel):
    """Bivariate correlation analysis result."""

    pearson_r: float | None = Field(
        default=None,
        description="Pearson product-moment correlation coefficient",
    )
    spearman_r: float | None = Field(
        default=None,
        description="Spearman rank-order correlation coefficient",
    )
    p_value: float | None = Field(
        default=None,
        description="Two-tailed p-value for the Pearson correlation",
    )
    interpretation: str = Field(
        ...,
        description="Qualitative policy-relevant interpretation of correlation strength and direction",
    )
    error: str | None = Field(
        default=None,
        description="Error indicator if computation was unable to proceed",
    )

    model_config = ConfigDict(from_attributes=True)


class StatsResult(BaseModel):
    """Consolidated statistical analysis result aggregation."""

    trend: TrendResult | None = Field(
        default=None,
        description="Trend regression and YoY growth results",
    )
    summary: SummaryResult | None = Field(
        default=None,
        description="Summary descriptive statistics",
    )
    sector_shares: SectorShareResult | None = Field(
        default=None,
        description="Sector distribution breakdown",
    )
    correlations: list[CorrelationResult] = Field(
        default_factory=list,
        description="List of bivariate correlation results",
    )
    comparison: dict[str, Any] | None = Field(
        default=None,
        description="Direct comparative analysis across evaluation periods or categories",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata and source info",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("correlations", mode="before")
    @classmethod
    def normalize_correlations(cls, v: Any) -> list[Any]:
        """Allow passing a single CorrelationResult or None and normalize to list."""
        if v is None:
            return []
        if isinstance(v, (CorrelationResult, dict)):
            return [v]
        return list(v)
