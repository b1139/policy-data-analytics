"""Unit tests for FastAPI health check endpoints and service probes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client fixture."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint returns 200 and platform metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "Agentic Policy Data Analytics" in data["app"]
    assert data["status"] == "operational"
    assert data["docs"] == "/docs"
    assert data["api_v1"] == "/api/v1"


def test_health_endpoint_structure(client):
    """Test unified /api/v1/health returns expected schema keys."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] in ("ok", "error")
    assert data["redis"] in ("ok", "error")
    assert "timestamp" in data
    # Validate timestamp is ISO8601 parsable
    parsed_time = datetime.fromisoformat(data["timestamp"])
    assert parsed_time is not None
    assert "environment" in data
    assert "llm" in data
    assert "primary" in data["llm"]
    assert "fallback" in data["llm"]
    assert "provider" in data["llm"]["primary"]
    assert "status" in data["llm"]["primary"]
    assert "provider" in data["llm"]["fallback"]
    assert "status" in data["llm"]["fallback"]


def test_no_redundant_health_endpoints(client):
    """Verify that redundant legacy endpoints (/health, /health/live, /api/v1/health/live) are not exposed."""
    for path in ["/health", "/health/live", "/api/v1/health/live"]:
        response = client.get(path)
        assert response.status_code == 404


def test_health_endpoint_check_llm_flag(client):
    """Test /api/v1/health?check_llm=false returns null for llm field."""
    response = client.get("/api/v1/health?check_llm=false")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["llm"] is None


def test_health_endpoint_caching_and_force(client):
    """Test that LLM health check status is cached and force_llm_check bypasses cache."""
    from app.api.v1.health import reset_health_cache
    from app.llm.router import LLMRouter, get_llm_router

    reset_health_cache()

    mock_router = MagicMock(spec=LLMRouter)
    mock_router.check_health = AsyncMock(
        return_value={
            "primary": {"provider": "gemini", "status": "ok", "latency_ms": 10.0},
            "fallback": {"provider": "bedrock", "status": "ok", "latency_ms": 20.0},
        }
    )

    app.dependency_overrides[get_llm_router] = lambda: mock_router
    try:
        # First call: triggers live probe
        res1 = client.get("/api/v1/health")
        assert res1.status_code == 200
        assert mock_router.check_health.call_count == 1

        # Second call: within 60s, uses cache (call_count should remain 1)
        res2 = client.get("/api/v1/health")
        assert res2.status_code == 200
        assert mock_router.check_health.call_count == 1

        # Third call: with force_llm_check=true, forces live probe (call_count becomes 2)
        res3 = client.get("/api/v1/health?force_llm_check=true")
        assert res3.status_code == 200
        assert mock_router.check_health.call_count == 2
    finally:
        app.dependency_overrides.clear()
        reset_health_cache()
