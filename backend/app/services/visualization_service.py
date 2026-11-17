"""Plotly visualization service for generating interactive policy charts."""

import json
import logging
from typing import Any

import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


class VisualizationService:
    """Service for generating interactive Plotly chart specifications.

    All methods produce JSON-serializable dictionaries compliant with Plotly's
    JSON schema for client-side interactive rendering. Server-side rendering
    (e.g., fig.show()) is strictly avoided.
    """

    DEFAULT_COLOR: str = "#0F5FA6"  # Singapore Government Blue
    ACCENT_COLOR: str = "#F4A201"  # Policy Amber Accent
    PALETTE: list[str] = [
        "#0F5FA6",  # Singapore Blue
        "#F4A201",  # Amber
        "#2A9D8F",  # Teal
        "#E76F51",  # Coral
        "#264653",  # Dark Teal
        "#E9C46A",  # Gold
        "#7209B7",  # Purple
        "#0077B6",  # Light Blue
    ]

    EMPTY_CHART: dict[str, str] = {
        "error": "no_data",
        "type": "empty_chart",
    }

    @classmethod
    def _create_source_annotation(cls, source_label: str) -> dict[str, Any]:
        """Generate standardized bottom-right data source citation annotation."""
        label_text = source_label.strip() if source_label else "Singapore Official Statistics"
        if not label_text.lower().startswith("source:"):
            label_text = f"Source: {label_text}"

        return {
            "text": label_text,
            "xref": "paper",
            "yref": "paper",
            "x": 1.0,
            "y": -0.18,
            "showarrow": False,
            "xanchor": "right",
            "yanchor": "top",
            "font": {"size": 10, "color": "#64748B"},
        }

    @classmethod
    def line_chart(
        cls,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str,
        source_label: str,
        color: str | None = None,
    ) -> dict[str, Any]:
        """Generate a single-series Plotly line chart with markers.

        Args:
            df: Input pandas DataFrame.
            x_col: Column name for the horizontal/time axis.
            y_col: Column name for the metric/vertical axis.
            title: Chart title.
            source_label: Attribution text for bottom-right citation annotation.
            color: Optional hex color override; defaults to SG Blue (#0F5FA6).

        Returns:
            Dictionary containing Plotly figure JSON spec ('data' and 'layout').
        """
        if (
            df is None
            or not isinstance(df, pd.DataFrame)
            or df.empty
            or x_col not in df.columns
            or y_col not in df.columns
        ):
            return cls.EMPTY_CHART.copy()

        clean_df = df[[x_col, y_col]].dropna()
        if clean_df.empty:
            return cls.EMPTY_CHART.copy()

        line_color = color or cls.DEFAULT_COLOR

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=clean_df[x_col].tolist(),
                y=clean_df[y_col].tolist(),
                mode="lines+markers",
                name=y_col,
                line={"color": line_color, "width": 2.5},
                marker={"size": 6, "color": line_color},
                hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
            )
        )

        fig.update_layout(
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            xaxis={"title": x_col, "gridcolor": "#E2E8F0"},
            yaxis={"title": y_col, "gridcolor": "#E2E8F0"},
            hovermode="closest",
            margin={"l": 50, "r": 30, "t": 60, "b": 60},
            annotations=[cls._create_source_annotation(source_label)],
        )

        return json.loads(fig.to_json())

    @classmethod
    def bar_chart(
        cls,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str,
        source_label: str,
        orientation: str = "v",
        color: str | None = None,
    ) -> dict[str, Any]:
        """Generate a vertical or horizontal Plotly bar chart.

        Args:
            df: Input pandas DataFrame.
            x_col: Column name for category (v) or metric (h).
            y_col: Column name for metric (v) or category (h).
            title: Chart title.
            source_label: Attribution text for bottom-right citation annotation.
            orientation: Bar orientation ('v' for vertical, 'h' for horizontal).
            color: Optional hex color override; defaults to SG Amber (#F4A201).

        Returns:
            Dictionary containing Plotly figure JSON spec ('data' and 'layout').
        """
        if (
            df is None
            or not isinstance(df, pd.DataFrame)
            or df.empty
            or x_col not in df.columns
            or y_col not in df.columns
        ):
            return cls.EMPTY_CHART.copy()

        clean_df = df[[x_col, y_col]].dropna()
        if clean_df.empty:
            return cls.EMPTY_CHART.copy()

        bar_color = color or cls.ACCENT_COLOR
        fig = go.Figure()

        if orientation == "h":
            fig.add_trace(
                go.Bar(
                    x=clean_df[y_col].tolist(),
                    y=clean_df[x_col].tolist(),
                    orientation="h",
                    marker={"color": bar_color},
                    hovertemplate=f"<b>%{{y}}</b><br>{y_col}: %{{x:,.2f}}<extra></extra>",
                )
            )
            xaxis_title = y_col
            yaxis_title = x_col
        else:
            fig.add_trace(
                go.Bar(
                    x=clean_df[x_col].tolist(),
                    y=clean_df[y_col].tolist(),
                    orientation="v",
                    marker={"color": bar_color},
                    hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
                )
            )
            xaxis_title = x_col
            yaxis_title = y_col

        fig.update_layout(
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            xaxis={"title": xaxis_title, "gridcolor": "#E2E8F0"},
            yaxis={"title": yaxis_title, "gridcolor": "#E2E8F0"},
            hovermode="closest",
            margin={"l": 50, "r": 30, "t": 60, "b": 60},
            annotations=[cls._create_source_annotation(source_label)],
        )

        return json.loads(fig.to_json())

    @classmethod
    def multi_line_chart(
        cls,
        df: pd.DataFrame,
        x_col: str,
        y_cols: list[str],
        title: str,
        source_label: str,
        colors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a multi-series line chart comparing sectors or indicators.

        Args:
            df: Input pandas DataFrame.
            x_col: Column name for the horizontal/time axis.
            y_cols: List of column names representing different comparison series.
            title: Chart title.
            source_label: Attribution text for bottom-right citation annotation.
            colors: Optional list of hex color overrides.

        Returns:
            Dictionary containing Plotly figure JSON spec ('data' and 'layout').
        """
        if (
            df is None
            or not isinstance(df, pd.DataFrame)
            or df.empty
            or x_col not in df.columns
            or not y_cols
        ):
            return cls.EMPTY_CHART.copy()

        valid_y_cols = [c for c in y_cols if c in df.columns]
        if not valid_y_cols:
            return cls.EMPTY_CHART.copy()

        clean_df = df[[x_col] + valid_y_cols].dropna(how="all", subset=valid_y_cols)
        if clean_df.empty:
            return cls.EMPTY_CHART.copy()

        palette = colors or cls.PALETTE
        fig = go.Figure()

        for idx, col in enumerate(valid_y_cols):
            series_color = palette[idx % len(palette)]
            fig.add_trace(
                go.Scatter(
                    x=clean_df[x_col].tolist(),
                    y=clean_df[col].tolist(),
                    mode="lines+markers",
                    name=col,
                    line={"color": series_color, "width": 2.2},
                    marker={"size": 5, "color": series_color},
                    hovertemplate=f"<b>%{{x}}</b><br>{col}: %{{y:,.2f}}<extra></extra>",
                )
            )

        fig.update_layout(
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            xaxis={"title": x_col, "gridcolor": "#E2E8F0"},
            yaxis={"title": "Value", "gridcolor": "#E2E8F0"},
            hovermode="closest",
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1.0,
            },
            margin={"l": 50, "r": 30, "t": 70, "b": 60},
            annotations=[cls._create_source_annotation(source_label)],
        )

        return json.loads(fig.to_json())

    @classmethod
    def heatmap(
        cls,
        df: pd.DataFrame,
        title: str,
        source_label: str = "SingStat",
        colorscale: str = "Blues",
    ) -> dict[str, Any]:
        """Generate a correlation or matrix heatmap.

        Args:
            df: 2D pandas DataFrame (typically correlation or cross-tabulation).
            title: Chart title.
            source_label: Attribution text for bottom-right citation annotation.
            colorscale: Plotly colorscale identifier (defaults to 'Blues').

        Returns:
            Dictionary containing Plotly figure JSON spec ('data' and 'layout').
        """
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return cls.EMPTY_CHART.copy()

        fig = go.Figure(
            data=go.Heatmap(
                z=df.values,
                x=list(df.columns),
                y=list(df.index),
                colorscale=colorscale,
                hoverongaps=False,
            )
        )

        fig.update_layout(
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            margin={"l": 60, "r": 30, "t": 60, "b": 60},
            annotations=[cls._create_source_annotation(source_label)],
        )

        return json.loads(fig.to_json())

    @classmethod
    def comparison_bar_chart(
        cls,
        df: pd.DataFrame,
        category_col: str,
        series_1_col: str,
        series_2_col: str,
        series_1_label: str = "2024",
        series_2_label: str = "2025",
        title: str = "Comparative Analysis",
        source_label: str = "Official Singapore Statistics",
        metric_label: str = "Value",
    ) -> dict[str, Any]:
        """Generate a dynamic grouped comparative bar chart comparing two periods side-by-side.

        Args:
            df: Input pandas DataFrame containing the categories and series data.
            category_col: Column containing group/category names (e.g. sectors or industries).
            series_1_col: Column for first comparison series (e.g. 2024).
            series_2_col: Column for second comparison series (e.g. 2025).
            series_1_label: Display label for first series.
            series_2_label: Display label for second series.
            title: Overall chart title.
            source_label: Attribution text for bottom-right citation annotation.
            metric_label: Y-axis title label.

        Returns:
            Dictionary containing Plotly figure JSON spec ('data' and 'layout').
        """
        if (
            df is None
            or not isinstance(df, pd.DataFrame)
            or df.empty
            or category_col not in df.columns
            or series_1_col not in df.columns
            or series_2_col not in df.columns
        ):
            return cls.EMPTY_CHART.copy()

        clean_df = (
            df[[category_col, series_1_col, series_2_col]]
            .dropna(how="all", subset=[series_1_col, series_2_col])
            .copy()
        )
        if clean_df.empty:
            return cls.EMPTY_CHART.copy()

        fig = go.Figure()

        # Trace 1: Series 1 (Singapore Blue)
        fig.add_trace(
            go.Bar(
                x=clean_df[category_col].tolist(),
                y=clean_df[series_1_col].tolist(),
                name=str(series_1_label),
                marker={"color": cls.DEFAULT_COLOR},
                hovertemplate=f"<b>%{{x}}</b><br>{series_1_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

        # Trace 2: Series 2 (Policy Amber Accent)
        fig.add_trace(
            go.Bar(
                x=clean_df[category_col].tolist(),
                y=clean_df[series_2_col].tolist(),
                name=str(series_2_label),
                marker={"color": cls.ACCENT_COLOR},
                hovertemplate=f"<b>%{{x}}</b><br>{series_2_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

        fig.update_layout(
            barmode="group",
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            xaxis={"title": category_col.replace("_", " ").title(), "gridcolor": "#E2E8F0"},
            yaxis={"title": metric_label.replace("_", " ").title(), "gridcolor": "#E2E8F0"},
            hovermode="closest",
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1.0,
            },
            margin={"l": 50, "r": 30, "t": 70, "b": 70},
            annotations=[cls._create_source_annotation(source_label)],
        )

        return json.loads(fig.to_json())

    @classmethod
    def pie_chart(
        cls,
        df: pd.DataFrame,
        label_col: str,
        value_col: str,
        title: str,
        source_label: str,
    ) -> dict[str, Any]:
        """Generate a donut chart showing each category's share of a total."""
        if (
            df is None
            or not isinstance(df, pd.DataFrame)
            or df.empty
            or label_col not in df.columns
            or value_col not in df.columns
        ):
            return cls.EMPTY_CHART.copy()

        clean_df = df[[label_col, value_col]].dropna()
        clean_df = clean_df[pd.to_numeric(clean_df[value_col], errors="coerce") > 0]
        if clean_df.empty:
            return cls.EMPTY_CHART.copy()

        fig = go.Figure(
            data=go.Pie(
                labels=clean_df[label_col].astype(str).tolist(),
                values=clean_df[value_col].tolist(),
                hole=0.4,
                marker={"colors": cls.PALETTE},
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{value:,.2f} (%{percent})<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white",
            title={"text": title, "x": 0.05, "xanchor": "left"},
            margin={"l": 30, "r": 30, "t": 60, "b": 60},
            annotations=[cls._create_source_annotation(source_label)],
        )
        return json.loads(fig.to_json())
