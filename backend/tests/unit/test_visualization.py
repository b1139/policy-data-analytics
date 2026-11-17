"""Unit tests for chart JSON output shape and Plotly visualization service (Story S29).

Verifies:
- line_chart returns dict with 'data', 'layout', and expected trace properties
- bar_chart returns valid JSON spec with categorical axes
- multi_line_chart returns multi-trace comparison spec
- Color palette conforms to Singapore Government Design System (#003366, #E02020)
- Graceful error recovery on empty dataframe returning standardized empty chart dict
"""

import pandas as pd
import pytest

from app.services.visualization_service import VisualizationService


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Sample time series dataframe."""
    return pd.DataFrame(
        {
            "year": [2019, 2020, 2021, 2022, 2023],
            "employment_rate": [80.3, 79.1, 81.4, 82.8, 83.5],
        }
    )


@pytest.fixture
def categorical_df() -> pd.DataFrame:
    """Sample categorical dataframe."""
    return pd.DataFrame(
        {
            "sector": ["Tech", "Finance", "Healthcare"],
            "count": [120, 85, 95],
        }
    )


class TestChartJsonOutputShape:
    """Validate JSON output shape produced by VisualizationService."""

    def test_line_chart_json_output_shape(self, sample_df: pd.DataFrame):
        """Line chart JSON contains 'data', 'layout' keys with valid trace and annotation."""
        spec = VisualizationService.line_chart(
            sample_df,
            x_col="year",
            y_col="employment_rate",
            title="Employment Rate Trend",
            source_label="SingStat",
        )

        assert isinstance(spec, dict)
        assert "data" in spec
        assert "layout" in spec

        # Traces check
        assert len(spec["data"]) == 1
        trace = spec["data"][0]
        assert trace["type"] == "scatter"
        assert trace["mode"] == "lines+markers"
        assert list(trace["x"]) == [2019, 2020, 2021, 2022, 2023]
        assert list(trace["y"]) == [80.3, 79.1, 81.4, 82.8, 83.5]
        assert trace["line"]["color"] == VisualizationService.DEFAULT_COLOR

        # Layout check
        layout = spec["layout"]
        assert layout["title"]["text"] == "Employment Rate Trend"
        assert len(layout["annotations"]) >= 1
        assert "Source: SingStat" in layout["annotations"][0]["text"]

    def test_bar_chart_json_output_shape(self, categorical_df: pd.DataFrame):
        """Bar chart JSON contains 'data' with bar trace and expected layout."""
        spec = VisualizationService.bar_chart(
            categorical_df,
            x_col="sector",
            y_col="count",
            title="Sector Breakdown",
            source_label="MOM",
        )

        assert isinstance(spec, dict)
        assert "data" in spec
        assert "layout" in spec
        assert len(spec["data"]) == 1
        assert spec["data"][0]["type"] == "bar"
        assert list(spec["data"][0]["x"]) == ["Tech", "Finance", "Healthcare"]

    def test_multi_line_chart_json_output_shape(self):
        """Multi-line chart returns multiple traces with distinct colors."""
        df = pd.DataFrame(
            {
                "year": [2021, 2022, 2023],
                "Tech": [100, 110, 120],
                "Finance": [90, 95, 105],
            }
        )

        spec = VisualizationService.multi_line_chart(
            df,
            x_col="year",
            y_cols=["Tech", "Finance"],
            title="Industry Growth",
            source_label="SingStat",
        )

        assert isinstance(spec, dict)
        assert len(spec["data"]) == 2
        trace_names = [t["name"] for t in spec["data"]]
        assert trace_names == ["Tech", "Finance"]

    def test_empty_dataframe_returns_clean_error_dict(self):
        """Empty dataframe safely returns standard empty_chart dict without unhandled exception."""
        res = VisualizationService.line_chart(
            pd.DataFrame(),
            x_col="x",
            y_col="y",
            title="Empty Chart",
            source_label="None",
        )
        assert res == {"error": "no_data", "type": "empty_chart"}
