"""Pydantic schemas for data quality validation and reporting."""

from typing import Any

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Structured report returned by the DataQualityValidator."""

    passed: bool = Field(
        ...,
        description="Indicates whether validation passed without critical errors.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of non-blocking quality warnings (e.g. outliers, missing values).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of critical validation errors (e.g. empty dataset, missing structure).",
    )
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Dataset summary statistics: row_count, col_count, null_pct_by_col, dtypes.",
    )

    def to_analysis_metadata(self) -> dict[str, Any]:
        """Convert validation result into dictionary suitable for analysis result metadata."""
        issues = list(self.warnings) + list(self.errors)
        return {
            "passed": self.passed,
            "data_quality_issues": issues,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "stats": self.stats,
        }
