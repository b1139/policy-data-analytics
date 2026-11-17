"""Tests for no-data handling and LLM-driven chart type selection."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.agents.analytics import (
    _select_and_synthesize_chart,
    _synthesize_intelligent_chart,
    analytics_node,
)
from app.agents.state import create_initial_state
from app.agents.tools.analysis_tools import compute_statistics
from app.llm.base import LLMResponse

DF = pd.DataFrame(
    {
        "year": [2023, 2023, 2024, 2024],
        "sector": ["ICT", "Finance", "ICT", "Finance"],
        "employment_count": [100.0, 80.0, 110.0, 85.0],
    }
)
DATASET = {
    "dataset_id": "d1",
    "title": "Employment",
    "source": "SingStat",
    "df_json": DF.to_json(orient="records"),
}


def _router(content: str) -> MagicMock:
    r = MagicMock()
    r.complete = AsyncMock(return_value=LLMResponse(content=content, model="m", provider="p"))
    return r


def test_requested_period_missing_returns_no_data() -> None:
    res = compute_statistics.invoke({"df_json": DATASET["df_json"], "query": "employment in 2030"})
    assert res.get("error") == "no_data"
    assert _synthesize_intelligent_chart([DATASET], "employment in 2030") is None


@pytest.mark.asyncio
async def test_llm_chart_choice_is_used() -> None:
    router = _router(json.dumps({"chart_type": "pie", "reason": "share of total"}))
    with patch("app.services.chart_selector.get_llm_router", return_value=router):
        chart, sel = await _select_and_synthesize_chart([DATASET], "employment share by sector")
    assert sel["selected_by"] == "llm" and sel["chart_type"] == "pie"
    assert chart["data"][0]["type"] == "pie"


@pytest.mark.asyncio
async def test_invalid_llm_choice_falls_back_to_heuristic() -> None:
    with patch("app.services.chart_selector.get_llm_router", return_value=_router("not json")):
        chart, sel = await _select_and_synthesize_chart([DATASET], "employment trend")
    assert sel["selected_by"] == "heuristic"
    assert chart is not None


@pytest.mark.asyncio
async def test_node_no_data_when_period_not_in_dataset() -> None:
    state = create_initial_state(str(uuid.uuid4()), "employment in 2030")
    state["raw_datasets"] = [DATASET]
    with patch("app.agents.analytics.publish_step", new_callable=AsyncMock):
        res = await analytics_node(state)
    assert res["no_data"] is True
    assert res["charts"] == [] and res["insights"] == [] and res["stats"] == {}
