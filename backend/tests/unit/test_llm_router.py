"""Unit tests for LLM Router, exponential retry backoff, fallback failover, and health integration."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.llm.base import AbstractLLMProvider, LLMResponse
from app.llm.exceptions import AllProvidersFailedError, LLMProviderError
from app.llm.mock_provider import MockLLMProvider
from app.llm.router import LLMRouter, get_llm_router, reset_llm_router
from app.llm.router import logger as router_logger
from app.main import app


class DummyProvider(AbstractLLMProvider):
    """Test helper provider implementation."""

    def __init__(self, provider_name: str = "dummy", model: str = "dummy-model") -> None:
        self.provider_name = provider_name
        self.model = model
        self.complete_mock = AsyncMock()
        self.health_check_mock = AsyncMock(return_value=True)

    async def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        return await self.complete_mock(messages, **kwargs)

    async def health_check(self) -> bool:
        return await self.health_check_mock()


@pytest.fixture(autouse=True)
def clear_router_cache(caplog):
    """Ensure cached router instances are reset and log capture level is INFO."""
    logging.getLogger().setLevel(logging.INFO)
    router_logger.disabled = False
    router_logger.setLevel(logging.INFO)
    router_logger.propagate = True
    caplog.set_level(logging.INFO)
    reset_llm_router()
    yield
    reset_llm_router()


@pytest.fixture
def test_messages():
    """Standard message payload for testing."""
    return [{"role": "user", "content": "Analyze labor productivity trends"}]


@pytest.fixture
def dummy_response():
    """Sample successful LLMResponse."""
    return LLMResponse(
        content="Productivity increased by 2.3% year-on-year.",
        model="primary-model",
        provider="dummy-primary",
        usage={"input_tokens": 10, "output_tokens": 15, "total_tokens": 25},
        latency_ms=45.2,
    )


@pytest.mark.asyncio
async def test_primary_success(test_messages, dummy_response, caplog):
    """Test primary provider succeeds on the first attempt without touching fallback."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")
    primary.complete_mock.return_value = dummy_response

    router = LLMRouter(primary=primary, fallback=fallback, backoff_factor=0.0)

    with caplog.at_level("INFO"):
        response = await router.complete(test_messages)

    assert response == dummy_response
    assert primary.complete_mock.call_count == 1
    assert fallback.complete_mock.call_count == 0
    assert "Using primary: gemini" in caplog.text


@pytest.mark.asyncio
async def test_primary_retry_then_success(test_messages, dummy_response, caplog):
    """Test primary provider retries on transient error and succeeds on 2nd attempt."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    transient_error = LLMProviderError(
        "Connection reset by peer. 503 Service Unavailable.",
        provider="gemini",
        is_retryable=True,
    )
    primary.complete_mock.side_effect = [transient_error, dummy_response]

    router = LLMRouter(primary=primary, fallback=fallback, max_retries=3, backoff_factor=0.0)

    with caplog.at_level("INFO"):
        response = await router.complete(test_messages)

    assert response == dummy_response
    assert primary.complete_mock.call_count == 2
    assert fallback.complete_mock.call_count == 0
    assert "Using primary: gemini" in caplog.text


@pytest.mark.asyncio
async def test_primary_failure_fallback_success(test_messages, caplog):
    """Test primary provider fails 3 times, router falls back to secondary provider and succeeds."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    transient_error = LLMProviderError(
        "Connection timeout 504.",
        provider="gemini",
        is_retryable=True,
    )
    fallback_response = LLMResponse(
        content="Fallback analysis complete.",
        model="bedrock-claude",
        provider="bedrock",
        usage={"input_tokens": 12, "output_tokens": 20, "total_tokens": 32},
        latency_ms=62.0,
    )

    primary.complete_mock.side_effect = transient_error
    fallback.complete_mock.return_value = fallback_response

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=True,
        max_retries=3,
        backoff_factor=0.0,
    )

    with caplog.at_level("INFO"):
        response = await router.complete(test_messages)

    assert response == fallback_response
    assert primary.complete_mock.call_count == 3
    assert fallback.complete_mock.call_count == 1
    assert "Using primary: gemini" in caplog.text
    assert "Primary failed, using fallback: bedrock" in caplog.text


@pytest.mark.asyncio
async def test_primary_failure_fallback_disabled_raises_error(test_messages, caplog):
    """Test primary failure does not call fallback when llm_fallback=False (default)."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    transient_error = LLMProviderError(
        "Connection timeout 504.",
        provider="gemini",
        is_retryable=True,
    )
    primary.complete_mock.side_effect = transient_error

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=False,
        max_retries=3,
        backoff_factor=0.0,
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.complete(test_messages)

    assert primary.complete_mock.call_count == 3
    assert fallback.complete_mock.call_count == 0
    assert exc_info.value.primary_error == transient_error
    assert exc_info.value.fallback_error is None
    assert "fallback is disabled" in str(exc_info.value).lower()
    assert "fallback is disabled" in caplog.text.lower()


@pytest.mark.asyncio
async def test_primary_non_retryable_fails_fast_to_fallback(test_messages, caplog):
    """Test non-retryable error (e.g. auth 401) aborts primary retries immediately to fallback."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    auth_error = LLMProviderError(
        "Invalid API Key. 401 Unauthorized.",
        provider="gemini",
        is_retryable=False,
    )
    fallback_response = LLMResponse(
        content="Responded via fallback.",
        model="bedrock-model",
        provider="bedrock",
        usage={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        latency_ms=30.0,
    )

    primary.complete_mock.side_effect = auth_error
    fallback.complete_mock.return_value = fallback_response

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=True,
        max_retries=3,
        backoff_factor=0.0,
    )

    with caplog.at_level("INFO"):
        response = await router.complete(test_messages)

    assert response == fallback_response
    # Should fail fast after only 1 attempt
    assert primary.complete_mock.call_count == 1
    assert fallback.complete_mock.call_count == 1
    assert "non-retryable error; failing fast to fallback" in caplog.text
    assert "Primary failed, using fallback: bedrock" in caplog.text


@pytest.mark.asyncio
async def test_primary_non_retryable_fallback_disabled_raises_error(test_messages):
    """Test non-retryable error fails fast and raises error without calling fallback when llm_fallback=False."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    auth_error = LLMProviderError(
        "Invalid API Key. 401 Unauthorized.",
        provider="gemini",
        is_retryable=False,
    )
    primary.complete_mock.side_effect = auth_error

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=False,
        max_retries=3,
        backoff_factor=0.0,
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.complete(test_messages)

    assert primary.complete_mock.call_count == 1
    assert fallback.complete_mock.call_count == 0
    assert exc_info.value.primary_error == auth_error
    assert exc_info.value.fallback_error is None


@pytest.mark.asyncio
async def test_both_fail_raises_all_providers_failed_error(test_messages, caplog):
    """Test AllProvidersFailedError is raised with details from both when all providers fail."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    primary_error = LLMProviderError("Gemini quota exhausted", provider="gemini", is_retryable=True)
    fallback_error = LLMProviderError(
        "Bedrock service unavailable", provider="bedrock", is_retryable=True
    )

    primary.complete_mock.side_effect = primary_error
    fallback.complete_mock.side_effect = fallback_error

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=True,
        max_retries=3,
        backoff_factor=0.0,
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.complete(test_messages)

    exc = exc_info.value
    assert exc.primary_error == primary_error
    assert exc.fallback_error == fallback_error
    assert "Both primary ('gemini') and fallback ('bedrock')" in str(exc)
    assert primary.complete_mock.call_count == 3
    assert fallback.complete_mock.call_count == 1
    assert "Primary failed, using fallback: bedrock" in caplog.text


@pytest.mark.asyncio
async def test_invalid_messages_raises_value_error():
    """Test validation fails immediately for invalid messages format before LLM calls."""
    router = LLMRouter(mock_mode=True)

    with pytest.raises(ValueError, match="non-empty list"):
        await router.complete([])

    with pytest.raises(ValueError, match="Message at index 0 must be a dictionary"):
        await router.complete(["invalid string"])


@pytest.mark.asyncio
async def test_mock_mode_routing():
    """Test that mock_mode=True configures MockLLMProvider for both slots and produces valid responses."""
    router = LLMRouter(mock_mode=True)

    assert isinstance(router.primary, MockLLMProvider)
    assert isinstance(router.fallback, MockLLMProvider)

    # Keyword matching deterministic response
    resp = await router.complete([{"role": "user", "content": "foreign workforce evaluation"}])
    assert resp.provider == "mock"
    assert "COMPASS" in resp.content or "foreign workforce" in resp.content.lower()

    # JSON mode
    json_resp = await router.complete(
        [{"role": "user", "content": "employment"}],
        json_mode=True,
    )
    assert json_resp.provider == "mock"
    assert "resident_employment_rate" in json_resp.content


@pytest.mark.asyncio
async def test_router_check_health():
    """Test LLMRouter check_health and health_check methods across healthy and degraded states."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    # 1. Both healthy
    primary.health_check_mock.return_value = True
    fallback.health_check_mock.return_value = True
    router = LLMRouter(primary=primary, fallback=fallback)

    health_status = await router.check_health()
    assert health_status["primary"]["status"] == "ok"
    assert health_status["primary"]["provider"] == "gemini"
    assert "latency_ms" in health_status["primary"]
    assert health_status["fallback"]["status"] == "ok"
    assert health_status["fallback"]["provider"] == "bedrock"
    assert await router.health_check() is True

    # 2. Primary unhealthy, fallback healthy
    primary.health_check_mock.return_value = False
    fallback.health_check_mock.return_value = True

    health_status = await router.check_health()
    assert health_status["primary"]["status"] == "error"
    assert health_status["fallback"]["status"] == "ok"
    assert await router.health_check() is True

    # 3. Both unhealthy
    primary.health_check_mock.return_value = False
    fallback.health_check_mock.return_value = False

    health_status = await router.check_health()
    assert health_status["primary"]["status"] == "error"
    assert health_status["fallback"]["status"] == "error"
    assert await router.health_check() is False


@pytest.mark.asyncio
async def test_router_exponential_backoff_sleep_times():
    """Test that exponential backoff computes delay and calls asyncio.sleep with correct values."""
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    retryable_err = LLMProviderError("Throttled", provider="gemini", is_retryable=True)
    primary.complete_mock.side_effect = [
        retryable_err,
        retryable_err,
        LLMResponse("ok", "m", "gemini"),
    ]

    router = LLMRouter(primary=primary, fallback=fallback, max_retries=3, backoff_factor=1.0)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        resp = await router.complete([{"role": "user", "content": "hi"}])
        assert resp.content == "ok"
        # Attempt 0 sleep: 2^0 * 1.0 = 1.0; Attempt 1 sleep: 2^1 * 1.0 = 2.0
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


def test_get_llm_router_singleton():
    """Test get_llm_router caching and reset_llm_router cache clear behavior."""
    router1 = get_llm_router()
    router2 = get_llm_router()
    assert router1 is router2

    reset_llm_router()
    router3 = get_llm_router()
    assert router3 is not router1


def test_enriched_health_endpoint_response_with_llm_status():
    """Test /api/v1/health endpoint returns enriched LLM provider status."""
    client = TestClient(app)

    # Override get_llm_router with mock router
    mock_router = MagicMock(spec=LLMRouter)
    mock_router.check_health = AsyncMock(
        return_value={
            "primary": {"provider": "gemini", "status": "ok", "latency_ms": 14.5},
            "fallback": {"provider": "bedrock", "status": "ok", "latency_ms": 22.8},
        }
    )

    app.dependency_overrides[get_llm_router] = lambda: mock_router
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "llm" in data
        assert data["llm"]["primary"]["provider"] == "gemini"
        assert data["llm"]["primary"]["status"] == "ok"
        assert data["llm"]["primary"]["latency_ms"] == 14.5

        assert data["llm"]["fallback"]["provider"] == "bedrock"
        assert data["llm"]["fallback"]["status"] == "ok"
        assert data["llm"]["fallback"]["latency_ms"] == 22.8
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fallback_persists_for_remainder_of_query_and_resets_on_next_query(
    test_messages,
):
    """Test that once fallback occurs during a query, subsequent calls in that query bypass primary,

    and primary is only retried on the next user query.
    """
    primary = DummyProvider("gemini")
    fallback = DummyProvider("bedrock")

    transient_error = LLMProviderError(
        "Connection timed out 504.",
        provider="gemini",
        is_retryable=True,
    )
    fallback_resp_1 = LLMResponse(
        content="Step 1 fallback result", model="bedrock-1", provider="bedrock"
    )
    fallback_resp_2 = LLMResponse(
        content="Step 2 fallback result", model="bedrock-1", provider="bedrock"
    )
    primary_resp_q2 = LLMResponse(
        content="Query 2 primary result", model="gemini-1", provider="gemini"
    )

    # Primary will fail for query 1, but succeed for query 2
    primary.complete_mock.side_effect = [
        transient_error,
        transient_error,
        transient_error,
        primary_resp_q2,
    ]
    fallback.complete_mock.side_effect = [fallback_resp_1, fallback_resp_2]

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        llm_fallback=True,
        max_retries=3,
        backoff_factor=0.0,
    )

    query_1_id = "analysis-query-111"
    router.set_current_query(query_1_id)

    # 1. First call in query 1: Primary fails 3 times, falls back to bedrock and succeeds
    resp1 = await router.complete(test_messages)
    assert resp1 == fallback_resp_1
    assert primary.complete_mock.call_count == 3
    assert fallback.complete_mock.call_count == 1
    assert router.is_query_fallen_back(query_1_id) is True

    # 2. Second call in query 1 (e.g. analytics / chart generation in same query pipeline):
    # MUST NOT call primary at all!
    resp2 = await router.complete(test_messages)
    assert resp2 == fallback_resp_2
    assert primary.complete_mock.call_count == 3  # Unchanged! Did not touch primary!
    assert fallback.complete_mock.call_count == 2

    # Query 1 completes, clear query context
    router.clear_current_query(query_1_id)
    assert router.is_query_fallen_back(query_1_id) is False

    # 3. Next user input query: query 2 starts
    query_2_id = "analysis-query-222"
    router.set_current_query(query_2_id)
    assert router.is_query_fallen_back(query_2_id) is False

    # Primary SHOULD be retried for query 2!
    resp3 = await router.complete(test_messages)
    assert resp3 == primary_resp_q2
    assert primary.complete_mock.call_count == 4  # Primary was tried again!
    assert fallback.complete_mock.call_count == 2  # Fallback was not called!

    router.clear_current_query(query_2_id)


def test_user_friendly_error_formatting():
    """Verify that format_user_friendly_error removes stack traces and formats friendly status."""
    from app.llm.exceptions import format_user_friendly_error

    # 1. AllProvidersFailedError
    all_failed = AllProvidersFailedError(
        primary_error=ValueError(
            "Raw GoogleAPIError: 400 Bad Request\nTraceback (most recent call last):\nFile 'foo.py'"
        ),
        fallback_error=RuntimeError("Bedrock connection reset"),
    )
    friendly = format_user_friendly_error(all_failed)
    assert "Traceback" not in friendly
    assert "File 'foo.py'" not in friendly
    assert "AI service temporarily unavailable" in friendly

    # 2. Rate limit error
    rate_err = LLMProviderError(
        "429 Too Many Requests: Quota exceeded", provider="gemini", is_retryable=True
    )
    friendly_rate = format_user_friendly_error(rate_err)
    assert "Traceback" not in friendly_rate
    assert "busy or rate-limited" in friendly_rate or "high demand" in friendly_rate

    # 3. Traceback in general string
    raw_tb = "ValueError: Bad argument\nTraceback (most recent call last):\n  File '/app/main.py', line 42\n    raise err\nRuntimeError: connection lost"
    friendly_tb = format_user_friendly_error(raw_tb)
    assert "Traceback" not in friendly_tb
    assert "/app/main.py" not in friendly_tb
    assert "connection lost" in friendly_tb


@pytest.mark.asyncio
async def test_gemini_resource_exhaustion_stops_without_retry(test_messages):
    """Test that when Gemini hits resource exhaustion (429/quota):

    1. Primary Bedrock is used first.
    2. When Bedrock fails, it falls back to Gemini.
    3. When Gemini encounters resource exhaustion (429/quota), it stops immediately without retrying.
    4. Subsequent calls in the same query bypass Gemini and do not retry.
    5. On a new query, Bedrock is retried first, and Gemini is only retried if Bedrock fails.
    """
    primary = DummyProvider("bedrock")
    fallback = DummyProvider("gemini")

    bedrock_fail = LLMProviderError("AWS Bedrock timeout", provider="bedrock", is_retryable=False)
    gemini_exhausted = LLMProviderError(
        "ResourceExhausted: 429 Quota exceeded", provider="gemini", is_retryable=False
    )
    bedrock_ok = LLMResponse(
        content="Bedrock success on new request", model="bedrock-1", provider="bedrock"
    )

    # Query 1: Bedrock fails, then Gemini fails with resource exhaustion
    # For query 1 calls, Bedrock continues to fail; for query 2, Bedrock succeeds
    primary.complete_mock.side_effect = [bedrock_fail, bedrock_fail, bedrock_ok]
    fallback.complete_mock.side_effect = [gemini_exhausted]

    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        primary_name="bedrock",
        fallback_name="gemini",
        llm_fallback=True,
        max_retries=3,
        backoff_factor=0.0,
    )

    q1_id = "query-with-exhaustion"
    router.set_current_query(q1_id)

    # First attempt: Bedrock fails (1 attempt because non-retryable), Gemini fails (1 attempt because resource exhausted)
    with pytest.raises(AllProvidersFailedError):
        await router.complete(test_messages)

    assert primary.complete_mock.call_count == 1
    # Fallback Gemini must only be called ONCE - NO RETRIES!
    assert fallback.complete_mock.call_count == 1
    assert router.is_gemini_exhausted(q1_id) is True

    # Another call in the SAME query: must NOT call Gemini again
    with pytest.raises(AllProvidersFailedError):
        await router.complete(test_messages)
    # Gemini call count remains 1!
    assert fallback.complete_mock.call_count == 1

    # Query 2 (new user request):
    q2_id = "new-user-query"
    router.set_current_query(q2_id)
    assert router.is_gemini_exhausted(q2_id) is False

    # Bedrock succeeds! Gemini is NEVER called on the new request when primary is working!
    res_q2 = await router.complete(test_messages)
    assert res_q2.content == "Bedrock success on new request"
    assert fallback.complete_mock.call_count == 1  # Still 1, never touched!
