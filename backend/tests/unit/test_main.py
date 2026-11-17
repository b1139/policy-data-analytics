"""Unit tests for FastAPI app initialization, middleware, CORS, logging, and lifespan."""

import json
import logging
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging import JSONLogFormatter, RequestIdFilter, request_id_ctx
from app.core.redis import check_redis_health, close_redis_pool, get_redis, get_redis_pool
from app.main import app, lifespan


@pytest.fixture
def client():
    """Create test client fixture."""
    return TestClient(app)


def test_app_metadata():
    """Verify FastAPI application metadata and OpenAPI configurations."""
    assert app.title == settings.PROJECT_NAME
    assert app.version == "0.1.0"
    assert "Agentic Policy Data Analytics" in app.description
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
    assert len(app.openapi_tags) >= 3


def test_request_id_middleware_generates_uuid(client):
    """Verify request ID middleware generates a UUID when none is supplied."""
    response = client.get("/")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    generated_id = response.headers["X-Request-ID"]
    # Check that it is a valid UUID4
    parsed_uuid = uuid.UUID(generated_id, version=4)
    assert parsed_uuid is not None


def test_request_id_middleware_echoes_incoming_header(client):
    """Verify request ID middleware preserves and echoes custom correlation ID."""
    custom_id = "test-correlation-uuid-999"
    response = client.get("/", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_cors_middleware_allowed_origin(client):
    """Verify CORS headers returned for configured origin."""
    allowed_origin = "http://localhost:3000"
    response = client.get(
        "/",
        headers={"Origin": allowed_origin},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_middleware_preflight_options(client):
    """Verify CORS preflight OPTIONS request returns correct headers."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Request-ID, Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_structured_json_log_formatter():
    """Verify JSONLogFormatter outputs valid JSON with expected keys."""
    formatter = JSONLogFormatter()
    log_filter = RequestIdFilter()

    # Set context request ID
    token = request_id_ctx.set("req-test-12345")
    try:
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Structured log message %s",
            args=("success",),
            exc_info=None,
        )
        log_filter.filter(record)
        formatted_json = formatter.format(record)

        payload = json.loads(formatted_json)
        assert payload["level"] == "INFO"
        assert payload["name"] == "test_logger"
        assert payload["message"] == "Structured log message success"
        assert payload["request_id"] == "req-test-12345"
        assert "timestamp" in payload
    finally:
        request_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Verify lifespan context manager initializes DB and cleans up resources."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock) as mock_init_db,
        patch("app.main.close_db", new_callable=AsyncMock) as mock_close_db,
        patch("app.main.close_redis_pool", new_callable=AsyncMock) as mock_close_redis,
    ):
        async with lifespan(app):
            mock_init_db.assert_awaited_once()

        mock_close_redis.assert_awaited_once()
        mock_close_db.assert_awaited_once()


def test_redis_pool_singleton():
    """Verify get_redis_pool returns connection pool singleton."""
    pool1 = get_redis_pool()
    pool2 = get_redis_pool()
    assert pool1 is pool2


@pytest.mark.asyncio
async def test_check_redis_health_handles_exception():
    """Verify check_redis_health returns False cleanly when Redis is unreachable."""
    with patch("app.core.redis.get_redis_client", side_effect=ConnectionError("Redis down")):
        healthy = await check_redis_health()
        assert healthy is False


@pytest.mark.asyncio
async def test_get_redis_dependency():
    """Verify get_redis dependency yields a client and closes it."""
    mock_client = AsyncMock()
    with patch("app.core.redis.get_redis_client", return_value=mock_client):
        async for client in get_redis():
            assert client is mock_client
        mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_redis_pool():
    """Verify close_redis_pool disconnects pool and resets singleton."""
    pool = get_redis_pool()
    with patch.object(pool, "disconnect", new_callable=AsyncMock) as mock_disc:
        await close_redis_pool()
        mock_disc.assert_awaited_once()
