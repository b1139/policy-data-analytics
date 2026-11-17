"""Unit tests for FastAPI REST API endpoints (Story S29).

Verifies:
- POST /api/v1/analysis/start returns 201 with analysis_id and ws_url
- GET /api/v1/analysis/{id} returns 404 for non-existent ID
- GET /api/v1/health returns 200 with db and redis status
- GET /api/v1/analysis returns 200 and list of analyses
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestApiEndpoints:
    """REST API endpoint tests using test_client fixture."""

    @pytest.mark.asyncio
    async def test_start_analysis_success(self, test_client: AsyncClient):
        """POST /api/v1/analysis/start returns 201 Created and analysis_id, ws_url."""
        with patch("app.api.v1.analysis.run_analysis_pipeline", new_callable=AsyncMock):
            response = await test_client.post(
                "/api/v1/analysis/start",
                json={
                    "query": "Analyze unemployment trends in Singapore 2020-2024",
                    "user_id": "test-user-001",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "analysis_id" in data
        assert "ws_url" in data
        assert data["status"].lower() in ("pending", "running")
        assert data["analysis_id"] in data["ws_url"]
        assert "ws" in data["ws_url"]

    @pytest.mark.asyncio
    async def test_get_analysis_unknown_id_returns_404(self, test_client: AsyncClient):
        """GET /api/v1/analysis/{id} returns 404 Not Found for non-existent analysis."""
        random_id = str(uuid.uuid4())
        response = await test_client.get(f"/api/v1/analysis/{random_id}")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_health_endpoint(self, test_client: AsyncClient):
        """GET /api/v1/health returns 200 OK with db and redis status."""
        response = await test_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "db" in data
        assert "redis" in data
        assert data["db"] in ("ok", "error")
        assert data["redis"] in ("ok", "error")
        assert "timestamp" in data
        assert "environment" in data
        assert "llm" in data

    @pytest.mark.asyncio
    async def test_list_analyses_endpoint(self, test_client: AsyncClient):
        """GET /api/v1/analysis returns 200 OK and an array of items."""
        response = await test_client.get("/api/v1/analysis")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_start_analysis_empty_query_fails_validation(self, test_client: AsyncClient):
        """POST /api/v1/analysis/start rejects queries shorter than min length."""
        response = await test_client.post(
            "/api/v1/analysis/start",
            json={
                "query": "short",
            },
        )
        assert response.status_code == 422
