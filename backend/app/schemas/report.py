"""Pydantic schemas for final report assembly, charts, citations, and analysis results."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Citation(BaseModel):
    """Citation metadata for an official data source or publication."""

    source: str = Field(
        ...,
        description="Data provider or agency source name, e.g. SingStat, Ministry of Manpower",
    )
    title: str = Field(
        ...,
        description="Title or table name of the dataset or publication",
    )
    url: str | None = Field(
        default=None,
        description="Direct URL to dataset or official portal if available",
    )
    accessed: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when dataset was retrieved or report generated",
    )
    dataset_id: str = Field(
        default="unknown",
        description="Unique dataset identifier, table ID, or resource slug",
    )

    model_config = ConfigDict(from_attributes=True)


class ChartSpec(BaseModel):
    """Plotly chart specification for client-side interactive rendering."""

    type: str = Field(
        ...,
        description="Chart visualization type, e.g. line, bar, heatmap, donut",
    )
    title: str = Field(
        ...,
        description="Display title for the chart visualization",
    )
    spec: dict[str, Any] = Field(
        ...,
        description="Complete Plotly figure JSON dictionary specification ('data' and 'layout')",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_spec(cls, data: Any) -> Any:
        """Allow initializing ChartSpec directly from a raw Plotly figure dictionary."""
        if isinstance(data, dict):
            if "spec" in data and "type" in data and "title" in data:
                return data

            # Extract title if missing
            title = data.get("title")
            if not title:
                layout = data.get("layout")
                if isinstance(layout, dict):
                    t = layout.get("title")
                    if isinstance(t, dict):
                        title = t.get("text", "Visualization")
                    elif isinstance(t, str):
                        title = t
                if not title:
                    title = "Visualization"

            # Extract chart type if missing
            chart_type = data.get("type")
            if not chart_type and isinstance(data.get("data"), list) and data["data"]:
                first_trace = data["data"][0]
                if isinstance(first_trace, dict):
                    chart_type = first_trace.get("type", "chart")
            if not chart_type:
                chart_type = "chart"

            spec = data.get("spec", data)

            return {
                "type": str(chart_type),
                "title": str(title),
                "spec": spec,
            }
        return data


class AnalysisResult(BaseModel):
    """Final assembled intelligence report saved to analyses.result JSONB."""

    insights: str = Field(
        ...,
        description="LLM policy narrative grounded in deterministic statistical outputs",
    )
    charts: list[ChartSpec] = Field(
        default_factory=list,
        description="Interactive Plotly chart specifications",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Official data sources and publications cited in this analysis",
    )
    models_used: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Real-time AI models and providers invoked during execution",
    )
    stats_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Key summary metrics including trend_direction, peak_year, overall_change_pct, data_points_count",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the analysis result was assembled",
    )
    truncated_preview: str = Field(
        default="",
        description="First 200 characters of insights for summary and list views",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_defaults(cls, data: Any) -> Any:
        """Automatically compute truncated_preview if missing or ensure max length 200."""
        if isinstance(data, dict):
            insights = data.get("insights", "")
            if isinstance(insights, list):
                insights = "\n\n".join(str(i) for i in insights if i)
                data["insights"] = insights
            elif not isinstance(insights, str):
                insights = str(insights or "")
                data["insights"] = insights

            preview = data.get("truncated_preview")
            if not preview:
                data["truncated_preview"] = insights[:200]
            elif len(preview) > 200:
                data["truncated_preview"] = preview[:200]

            if "generated_at" not in data or data["generated_at"] is None:
                data["generated_at"] = datetime.now(UTC)
        return data
