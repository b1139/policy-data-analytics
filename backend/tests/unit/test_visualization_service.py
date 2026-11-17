"""Unit tests for Plotly visualization service and chart generation tools (Story S22)."""

from typing import Any

import pandas as pd
import pytest

from app.agents.tools.analysis_tools import generate_chart
from app.services.visualization_service import VisualizationService


@pytest.fixture
def sample_timeseries_df() -> pd.DataFrame:
    """Sample time series dataframe for employment rate trend."""
    return pd.DataFrame(
        {
            "year": [2019, 2020, 2021, 2022, 2023],
            "employment_rate": [80.3, 79.1, 81.4, 82.8, 83.5],
        }
    )


@pytest.fixture
def sample_sector_df() -> pd.DataFrame:
    """Sample categorical dataframe for sector employment distribution."""
    return pd.DataFrame(
        {
            "sector": ["Technology", "Finance", "Healthcare", "Manufacturing", "Retail"],
            "share": [34.5, 28.2, 16.1, 12.4, 8.8],
        }
    )


@pytest.fixture
def sample_multi_sector_df() -> pd.DataFrame:
    """Sample multi-series dataframe comparing employment rates across multiple sectors."""
    return pd.DataFrame(
        {
            "year": [2019, 2020, 2021, 2022, 2023],
            "Tech": [75.0, 77.5, 81.0, 84.5, 87.0],
            "Finance": [78.0, 78.5, 80.0, 82.0, 83.5],
            "Manufacturing": [70.0, 68.5, 69.0, 71.0, 71.5],
        }
    )


class TestVisualizationServiceLineChart:
    """Unit tests for single-series line chart generation."""

    def test_line_chart_valid_spec(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify line chart returns valid Plotly JSON specification with data and layout."""
        spec = VisualizationService.line_chart(
            df=sample_timeseries_df,
            x_col="year",
            y_col="employment_rate",
            title="Resident Employment Rate (2019-2023)",
            source_label="SingStat",
        )

        assert isinstance(spec, dict)
        assert "data" in spec
        assert "layout" in spec
        assert len(spec["data"]) == 1

        trace = spec["data"][0]
        assert trace["type"] == "scatter"
        assert trace["mode"] == "lines+markers"
        assert trace["name"] == "employment_rate"
        assert list(trace["x"]) == [2019, 2020, 2021, 2022, 2023]
        assert trace["line"]["color"] == VisualizationService.DEFAULT_COLOR

    def test_line_chart_source_annotation(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify line chart layout contains bottom-right source annotation."""
        spec = VisualizationService.line_chart(
            df=sample_timeseries_df,
            x_col="year",
            y_col="employment_rate",
            title="Resident Employment Rate",
            source_label="Ministry of Manpower (MOM)",
        )

        layout = spec["layout"]
        assert layout["template"]["layout"]["xaxis"] is not None  # template applied
        assert "annotations" in layout
        annotations = layout["annotations"]
        assert len(annotations) >= 1
        assert "Source: Ministry of Manpower (MOM)" in annotations[0]["text"]
        assert annotations[0]["xanchor"] == "right"
        assert annotations[0]["yanchor"] == "top"

    def test_line_chart_custom_color(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify custom color override is applied to line and markers."""
        custom_color = "#2A9D8F"
        spec = VisualizationService.line_chart(
            df=sample_timeseries_df,
            x_col="year",
            y_col="employment_rate",
            title="Employment Rate",
            source_label="SingStat",
            color=custom_color,
        )

        trace = spec["data"][0]
        assert trace["line"]["color"] == custom_color
        assert trace["marker"]["color"] == custom_color

    def test_line_chart_empty_dataframe(self) -> None:
        """Verify empty dataframe returns standardized empty chart error dict."""
        empty_df = pd.DataFrame()
        res = VisualizationService.line_chart(
            df=empty_df,
            x_col="year",
            y_col="value",
            title="Empty Chart",
            source_label="None",
        )
        assert res == {"error": "no_data", "type": "empty_chart"}

    def test_line_chart_missing_column(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify requesting non-existent column returns empty chart error dict."""
        res = VisualizationService.line_chart(
            df=sample_timeseries_df,
            x_col="year",
            y_col="non_existent_metric",
            title="Invalid Column",
            source_label="None",
        )
        assert res == {"error": "no_data", "type": "empty_chart"}

    def test_line_chart_none_dataframe(self) -> None:
        """Verify None dataframe returns empty chart error dict without crashing."""
        res = VisualizationService.line_chart(
            df=None,  # type: ignore[arg-type]
            x_col="year",
            y_col="value",
            title="None Dataframe",
            source_label="None",
        )
        assert res == {"error": "no_data", "type": "empty_chart"}


class TestVisualizationServiceBarChart:
    """Unit tests for vertical and horizontal bar chart generation."""

    def test_vertical_bar_chart(self, sample_sector_df: pd.DataFrame) -> None:
        """Verify vertical bar chart returns valid Plotly specification with default SG Amber color."""
        spec = VisualizationService.bar_chart(
            df=sample_sector_df,
            x_col="sector",
            y_col="share",
            title="Employment Share by Sector",
            source_label="Economic Survey of Singapore",
            orientation="v",
        )

        assert "data" in spec
        assert "layout" in spec
        trace = spec["data"][0]
        assert trace["type"] == "bar"
        assert trace["orientation"] == "v"
        assert trace["marker"]["color"] == VisualizationService.ACCENT_COLOR
        assert list(trace["x"]) == [
            "Technology",
            "Finance",
            "Healthcare",
            "Manufacturing",
            "Retail",
        ]

        layout = spec["layout"]
        assert layout["title"]["text"] == "Employment Share by Sector"
        assert "Source: Economic Survey of Singapore" in layout["annotations"][0]["text"]

    def test_horizontal_bar_chart(self, sample_sector_df: pd.DataFrame) -> None:
        """Verify horizontal bar chart assigns y to categories and x to metric values."""
        spec = VisualizationService.bar_chart(
            df=sample_sector_df,
            x_col="sector",
            y_col="share",
            title="Employment Share (Horizontal)",
            source_label="SingStat",
            orientation="h",
        )

        trace = spec["data"][0]
        assert trace["type"] == "bar"
        assert trace["orientation"] == "h"
        assert list(trace["y"]) == [
            "Technology",
            "Finance",
            "Healthcare",
            "Manufacturing",
            "Retail",
        ]
        assert list(trace["x"]) == [34.5, 28.2, 16.1, 12.4, 8.8]

    def test_bar_chart_custom_color(self, sample_sector_df: pd.DataFrame) -> None:
        """Verify custom color override for bar chart."""
        spec = VisualizationService.bar_chart(
            df=sample_sector_df,
            x_col="sector",
            y_col="share",
            title="Custom Bar Color",
            source_label="SingStat",
            color="#E76F51",
        )
        assert spec["data"][0]["marker"]["color"] == "#E76F51"

    def test_bar_chart_empty_dataframe(self) -> None:
        """Verify empty dataframe handling in bar chart."""
        res = VisualizationService.bar_chart(
            df=pd.DataFrame(),
            x_col="sector",
            y_col="share",
            title="Empty Bar",
            source_label="SingStat",
        )
        assert res == {"error": "no_data", "type": "empty_chart"}


class TestVisualizationServiceMultiLineChart:
    """Unit tests for multi-series comparative line charts."""

    def test_multi_line_chart_valid_spec(self, sample_multi_sector_df: pd.DataFrame) -> None:
        """Verify multi-line chart generates separate traces with markers for each series."""
        y_cols = ["Tech", "Finance", "Manufacturing"]
        spec = VisualizationService.multi_line_chart(
            df=sample_multi_sector_df,
            x_col="year",
            y_cols=y_cols,
            title="Employment Comparison across Sectors",
            source_label="SingStat & MOM",
        )

        assert "data" in spec
        assert len(spec["data"]) == 3

        traces = spec["data"]
        names = [t["name"] for t in traces]
        assert names == ["Tech", "Finance", "Manufacturing"]

        for t in traces:
            assert t["type"] == "scatter"
            assert t["mode"] == "lines+markers"
            assert len(t["x"]) == 5

        # Colors should be distinct across series from palette
        colors = [t["line"]["color"] for t in traces]
        assert len(set(colors)) == 3

        layout = spec["layout"]
        assert layout["legend"]["orientation"] == "h"
        assert "Source: SingStat & MOM" in layout["annotations"][0]["text"]

    def test_multi_line_chart_missing_columns(self, sample_multi_sector_df: pd.DataFrame) -> None:
        """Verify non-existent columns are filtered out gracefully."""
        spec = VisualizationService.multi_line_chart(
            df=sample_multi_sector_df,
            x_col="year",
            y_cols=["Tech", "InvalidSector"],
            title="Partial Missing Series",
            source_label="SingStat",
        )

        assert len(spec["data"]) == 1
        assert spec["data"][0]["name"] == "Tech"

    def test_multi_line_chart_all_missing_columns(
        self, sample_multi_sector_df: pd.DataFrame
    ) -> None:
        """Verify empty chart error dict when none of the requested series exist."""
        spec = VisualizationService.multi_line_chart(
            df=sample_multi_sector_df,
            x_col="year",
            y_cols=["SectorX", "SectorY"],
            title="All Missing Series",
            source_label="SingStat",
        )
        assert spec == {"error": "no_data", "type": "empty_chart"}


class TestVisualizationServiceHeatmap:
    """Unit tests for correlation matrix and heatmap visualization."""

    def test_heatmap_generation(self) -> None:
        """Verify 2D matrix renders as Plotly Heatmap with white template and annotations."""
        corr_df = pd.DataFrame(
            [[1.0, 0.85, -0.4], [0.85, 1.0, -0.2], [-0.4, -0.2, 1.0]],
            index=["GDP", "Employment", "Inflation"],
            columns=["GDP", "Employment", "Inflation"],
        )

        spec = VisualizationService.heatmap(
            df=corr_df,
            title="Economic Indicators Correlation Heatmap",
            source_label="SingStat",
        )

        assert "data" in spec
        assert spec["data"][0]["type"] == "heatmap"
        assert spec["data"][0]["x"] == ["GDP", "Employment", "Inflation"]
        assert "Source: SingStat" in spec["layout"]["annotations"][0]["text"]

    def test_heatmap_empty_dataframe(self) -> None:
        """Verify heatmap returns empty chart error dict on empty dataframe."""
        res = VisualizationService.heatmap(df=pd.DataFrame(), title="Empty Heatmap")
        assert res == {"error": "no_data", "type": "empty_chart"}


class TestGenerateChartToolWrapper:
    """Unit tests for the generate_chart LangChain tool wrapper."""

    def test_tool_direct_call_line_chart(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify generate_chart can be invoked directly as a Python callable."""
        result = generate_chart(
            data=sample_timeseries_df,
            chart_type="line",
            title="Direct Call Line Chart",
            source_label="SingStat",
            x_col="year",
            y_col="employment_rate",
        )

        assert isinstance(result, dict)
        assert "data" in result
        assert "layout" in result
        assert result["data"][0]["mode"] == "lines+markers"

    def test_tool_invoke_bar_chart(self, sample_sector_df: pd.DataFrame) -> None:
        """Verify generate_chart works with LangChain .invoke() interface."""
        result = generate_chart.invoke(
            {
                "data": sample_sector_df,
                "chart_type": "bar",
                "title": "Sector Distribution",
                "source_label": "MOM",
                "x_col": "sector",
                "y_col": "share",
                "orientation": "v",
            }
        )

        assert isinstance(result, dict)
        assert "data" in result
        assert result["data"][0]["type"] == "bar"

    @pytest.mark.asyncio
    async def test_tool_ainvoke_multi_line(self, sample_multi_sector_df: pd.DataFrame) -> None:
        """Verify generate_chart supports async .ainvoke() interface."""
        result = await generate_chart.ainvoke(
            {
                "data": sample_multi_sector_df,
                "chart_type": "multi_line",
                "title": "Sector Comparative Growth",
                "source_label": "SingStat",
                "x_col": "year",
                "y_cols": ["Tech", "Finance"],
            }
        )

        assert isinstance(result, dict)
        assert len(result["data"]) == 2

    def test_tool_accepts_json_split_string(self, sample_timeseries_df: pd.DataFrame) -> None:
        """Verify generate_chart parses split JSON strings from data fetching pipeline."""
        split_json = sample_timeseries_df.to_json(orient="split")
        result = generate_chart(
            data=split_json,
            chart_type="line",
            title="Parsed Split JSON Chart",
            x_col="year",
            y_col="employment_rate",
        )

        assert "data" in result
        assert len(result["data"][0]["x"]) == 5

    def test_tool_accepts_records_list(self) -> None:
        """Verify generate_chart parses list of dictionaries (records format)."""
        records = [
            {"year": 2021, "gdp_growth": 7.6},
            {"year": 2022, "gdp_growth": 3.6},
            {"year": 2023, "gdp_growth": 1.1},
        ]

        result = generate_chart(
            data=records,
            chart_type="bar",
            title="GDP Growth Rate",
            x_col="year",
            y_col="gdp_growth",
        )

        assert "data" in result
        assert result["data"][0]["type"] == "bar"

    def test_tool_empty_data_handling(self) -> None:
        """Verify generate_chart handles empty or invalid data gracefully."""
        res = generate_chart(data=[], chart_type="line")
        assert res["type"] == "empty_chart"

        res_str = generate_chart(data="", chart_type="bar")
        assert res_str["type"] == "empty_chart"

    def test_no_server_side_show_called(
        self, monkeypatch: pytest.MonkeyPatch, sample_timeseries_df: pd.DataFrame
    ) -> None:
        """Verify fig.show() is never invoked during chart generation."""
        import plotly.graph_objects as go

        def mock_show(*_args: Any, **_kwargs: Any) -> None:
            pytest.fail("fig.show() should never be called in server-side chart generation!")

        monkeypatch.setattr(go.Figure, "show", mock_show)

        # Execute all chart functions
        VisualizationService.line_chart(sample_timeseries_df, "year", "employment_rate", "T", "S")
        VisualizationService.bar_chart(sample_timeseries_df, "year", "employment_rate", "T", "S")
        VisualizationService.multi_line_chart(
            sample_timeseries_df, "year", ["employment_rate"], "T", "S"
        )
        VisualizationService.heatmap(sample_timeseries_df, "T", "S")
        generate_chart(data=sample_timeseries_df, chart_type="line", title="T")
