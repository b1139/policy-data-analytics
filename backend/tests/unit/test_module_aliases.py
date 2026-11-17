"""Unit tests for module exports and aliases (Story coverage).

Covers:
- backend/app/services/insight_service.py
- backend/app/agents/llm_tools.py
- backend/app/agents/tools/llm_tools.py
- backend/app/api/websocket.py
"""

from fastapi import APIRouter

import app.agents.llm_tools as root_llm_tools
import app.agents.tools.llm_tools as sub_llm_tools
import app.api.websocket as root_websocket
import app.services.insight_service as insight_service
from app.agents.tools.analysis_tools import generate_insight
from app.api.v1.websocket import router as v1_router
from app.api.v1.websocket import websocket_analysis_endpoint
from app.services.analysis_service import InsightGenerator


def test_insight_service_exports():
    """Verify backend/app/services/insight_service.py re-exports InsightGenerator."""
    assert insight_service.InsightGenerator is InsightGenerator
    assert "InsightGenerator" in insight_service.__all__
    # Instantiate to exercise basic constructor
    generator = insight_service.InsightGenerator()
    assert generator is not None
    assert hasattr(generator, "generate_insights")


def test_agents_llm_tools_exports():
    """Verify backend/app/agents/llm_tools.py re-exports generate_insight."""
    assert root_llm_tools.generate_insight is generate_insight
    assert "generate_insight" in root_llm_tools.__all__
    assert hasattr(root_llm_tools.generate_insight, "invoke")
    assert root_llm_tools.generate_insight.name == "generate_insight"


def test_agents_tools_llm_tools_exports():
    """Verify backend/app/agents/tools/llm_tools.py re-exports generate_insight."""
    assert sub_llm_tools.generate_insight is generate_insight
    assert "generate_insight" in sub_llm_tools.__all__
    assert hasattr(sub_llm_tools.generate_insight, "invoke")
    assert sub_llm_tools.generate_insight.name == "generate_insight"


def test_api_websocket_exports():
    """Verify backend/app/api/websocket.py re-exports v1 websocket router and endpoint."""
    assert root_websocket.router is v1_router
    assert isinstance(root_websocket.router, APIRouter)
    assert root_websocket.websocket_analysis_endpoint is websocket_analysis_endpoint
    assert callable(root_websocket.websocket_analysis_endpoint)
    assert "router" in root_websocket.__all__
    assert "websocket_analysis_endpoint" in root_websocket.__all__
