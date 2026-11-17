"""Unit tests for concrete LLM providers (Gemini, Bedrock, OpenAI, Anthropic)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from app.llm import (
    AnthropicProvider,
    BedrockProvider,
    GeminiProvider,
    LLMProviderError,
    OpenAIProvider,
    convert_messages_to_langchain,
    extract_token_usage,
    is_retryable_error,
    mask_key,
)


def _create_mock_aimessage(
    content: str,
    input_tokens: int = 15,
    output_tokens: int = 25,
) -> AIMessage:
    """Helper to construct an AIMessage with usage metadata."""
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class TestUtilsAndExceptions:
    """Test helper utilities, masking, and error classification."""

    def test_mask_key(self) -> None:
        """Verify API key masking obscures sensitive characters."""
        assert mask_key("AIzaSyD123456789") == "AIza...****"
        assert mask_key("sk-proj-1234567890abcdef") == "sk-p...****"
        assert mask_key("AKIAIOSFODNN7EXAMPLE") == "AKIA...****"
        assert mask_key("short") == "shor...****"
        assert mask_key("abc") == "****"
        assert mask_key(None) == "[NOT_SET]"
        assert mask_key("") == "[NOT_SET]"

    def test_is_retryable_error(self) -> None:
        """Verify retryable classification across errors and status codes."""
        # Standard exceptions
        assert is_retryable_error(TimeoutError("Request timed out")) is True
        assert is_retryable_error(ConnectionResetError("Connection reset by peer")) is True
        assert is_retryable_error(ValueError("Invalid argument format")) is False

        # Status code attribute
        err_429 = Exception("Too Many Requests")
        err_429.status_code = 429
        assert is_retryable_error(err_429) is True

        err_529 = Exception("Overloaded")
        err_529.status_code = 529
        assert is_retryable_error(err_529) is True

        err_401 = Exception("Unauthorized")
        err_401.status_code = 401
        assert is_retryable_error(err_401) is False

        # AWS error dictionary
        aws_throttle = Exception("Rate exceeded")
        aws_throttle.response = {"Error": {"Code": "ThrottlingException"}}
        assert is_retryable_error(aws_throttle) is True

        aws_model_timeout = Exception("Model timeout")
        aws_model_timeout.response = {"Error": {"Code": "ModelTimeoutException"}}
        assert is_retryable_error(aws_model_timeout) is True

        aws_validation = Exception("Validation error")
        aws_validation.response = {"Error": {"Code": "ValidationException"}}
        assert is_retryable_error(aws_validation) is False

    def test_extract_token_usage_fallback(self) -> None:
        """Verify token extraction from different structures."""
        # Direct dictionary
        data_dict = {"usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}
        usage = extract_token_usage(data_dict)
        assert usage == {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}

        # Object with response_metadata
        mock_obj = MagicMock()
        mock_obj.usage_metadata = None
        mock_obj.response_metadata = {
            "token_usage": {"prompt_tokens": 5, "completion_tokens": 15, "total_tokens": 20}
        }
        usage2 = extract_token_usage(mock_obj)
        assert usage2 == {"input_tokens": 5, "output_tokens": 15, "total_tokens": 20}

    def test_convert_messages_to_langchain_json_mode(self) -> None:
        """Verify message conversion injects JSON instruction in json_mode."""
        msgs = [{"role": "user", "content": "Analyze employment"}]
        lc = convert_messages_to_langchain(msgs, json_mode=True, enforce_json_instruction=True)
        assert len(lc) == 2
        assert "Respond with valid JSON only." in lc[0].content


class TestGeminiProvider:
    """Test Google Gemini provider implementation with mocked SDK."""

    @pytest.mark.asyncio
    async def test_successful_complete(self) -> None:
        """Verify successful Gemini complete call returns formatted LLMResponse."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage("Gemini analysis of foreign workforce.")
        )
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(
            api_key="fake-gemini-key",
            model="gemini-1.5-flash",
            client=mock_client,
        )

        messages = [
            {"role": "system", "content": "You are a policy analyst."},
            {"role": "user", "content": "Analyze foreign workforce trends."},
        ]

        resp = await provider.complete(messages, temperature=0.5, max_tokens=500)
        assert resp.provider == "gemini"
        assert resp.model == "gemini-1.5-flash"
        assert resp.content == "Gemini analysis of foreign workforce."
        assert resp.usage["input_tokens"] == 15
        assert resp.usage["output_tokens"] == 25
        assert resp.usage["total_tokens"] == 40
        assert resp.latency_ms > 0

        # Verify bind was called with correct generation_config parameters
        mock_client.bind.assert_called_once_with(
            generation_config={"temperature": 0.5, "max_output_tokens": 500}
        )

    @pytest.mark.asyncio
    async def test_json_mode_sets_mime_type(self) -> None:
        """Verify json_mode=True binds response_mime_type='application/json'."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage('{"status": "ok", "trend": "positive"}')
        )
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(
            api_key="fake-gemini-key",
            client=mock_client,
        )

        resp = await provider.complete(
            [{"role": "user", "content": "Return metrics"}],
            json_mode=True,
        )
        parsed = json.loads(resp.content)
        assert parsed["status"] == "ok"

        mock_client.bind.assert_called_once_with(
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
                "response_mime_type": "application/json",
            }
        )

    @pytest.mark.asyncio
    async def test_health_check_success_and_failure(self) -> None:
        """Verify health check probe returns True on success and False on error."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(return_value=_create_mock_aimessage("pong"))
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(api_key="fake-gemini-key", client=mock_client)
        assert await provider.health_check() is True

        # Error case
        mock_bound.ainvoke = AsyncMock(side_effect=Exception("API connection refused"))
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_retryable_error_mapping(self) -> None:
        """Verify rate limits and connection errors raise retryable LLMProviderError."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        rate_limit_err = Exception("ResourceExhausted: 429 Quota exceeded")
        rate_limit_err.status_code = 429
        mock_bound.ainvoke = AsyncMock(side_effect=rate_limit_err)
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(api_key="fake-gemini-key", client=mock_client)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "gemini"
        # Per requirement: Gemini resource exhaustion stops immediately and is not retryable
        assert exc_info.value.is_retryable is False
        assert exc_info.value.original_error == rate_limit_err

    @pytest.mark.asyncio
    async def test_transient_timeout_error_mapping(self) -> None:
        """Verify transient network timeout raises retryable LLMProviderError on Gemini."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        timeout_err = TimeoutError("Connection timed out")
        mock_bound.ainvoke = AsyncMock(side_effect=timeout_err)
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(api_key="fake-gemini-key", client=mock_client)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "gemini"
        assert exc_info.value.is_retryable is True

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_non_retryable(self) -> None:
        """Verify unconfigured API key raises non-retryable LLMProviderError."""
        provider = GeminiProvider(api_key="", client=None)
        provider.api_key = None
        provider._client = None

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "gemini"
        assert exc_info.value.is_retryable is False

    @pytest.mark.asyncio
    async def test_timeout_triggers_retryable_error(self) -> None:
        """Verify request timeout raises retryable LLMProviderError."""
        import asyncio

        mock_client = MagicMock()
        mock_bound = MagicMock()

        async def slow_ainvoke(*_args, **_kwargs):
            await asyncio.sleep(0.5)
            return _create_mock_aimessage("Too late")

        mock_bound.ainvoke = slow_ainvoke
        mock_client.bind.return_value = mock_bound

        provider = GeminiProvider(api_key="fake-key", client=mock_client, timeout=0.05)
        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "gemini"
        assert exc_info.value.is_retryable is True
        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_real_chat_google_generative_ai_passes_generation_config(self) -> None:
        """Regression test: ChatGoogleGenerativeAI binds generation_config instead of top-level temperature."""
        provider = GeminiProvider(
            api_key="fake-gemini-key",
            model="gemini-1.5-flash",
        )
        assert provider._client is not None
        bound = provider._get_client(
            temperature=0.2,
            max_tokens=42,
            json_mode=True,
        )
        assert hasattr(bound, "kwargs")
        gen_config = bound.kwargs.get("generation_config", {})
        assert gen_config.get("temperature") == 0.2
        assert gen_config.get("max_output_tokens") == 42
        assert gen_config.get("response_mime_type") == "application/json"


class TestBedrockProvider:
    """Test Amazon Bedrock provider implementation with mocked SDK."""

    @pytest.mark.asyncio
    async def test_successful_complete(self) -> None:
        """Verify successful Bedrock complete call returns formatted LLMResponse."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage("Bedrock Claude output on demographic shifts.")
        )
        mock_client.bind.return_value = mock_bound

        provider = TestBedrockProvider._build_provider(mock_client)

        messages = [
            {"role": "system", "content": "You are a policy analyst."},
            {"role": "user", "content": "Analyze demographic shifts."},
        ]

        resp = await provider.complete(messages, temperature=0.3, max_tokens=800)
        assert resp.provider == "bedrock"
        assert resp.model == "anthropic.claude-3-5-sonnet-20240620-v1:0"
        assert resp.content == "Bedrock Claude output on demographic shifts."
        assert resp.usage["total_tokens"] == 40
        assert resp.latency_ms > 0

        mock_client.bind.assert_called_once_with(temperature=0.3, max_tokens=800)

    @staticmethod
    def _build_provider(client: MagicMock) -> BedrockProvider:
        return BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="ap-south-2",
            client=client,
        )

    @pytest.mark.asyncio
    async def test_json_mode_and_health_check(self) -> None:
        """Verify Bedrock JSON mode and health check probe."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage('{"metric": "gdp_growth", "value": 3.2}')
        )
        mock_client.bind.return_value = mock_bound

        provider = TestBedrockProvider._build_provider(mock_client)

        resp = await provider.complete([{"role": "user", "content": "Get GDP"}], json_mode=True)
        data = json.loads(resp.content)
        assert data["metric"] == "gdp_growth"

        # Health check
        assert await provider.health_check() is True

        # Failed health check
        mock_bound.ainvoke = AsyncMock(side_effect=Exception("Bedrock unavailable"))
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_retryable_throttling_error(self) -> None:
        """Verify AWS ThrottlingException flags is_retryable=True."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        throttle_err = Exception("ThrottlingException: Rate exceeded")
        throttle_err.response = {"Error": {"Code": "ThrottlingException"}}
        mock_bound.ainvoke = AsyncMock(side_effect=throttle_err)
        mock_client.bind.return_value = mock_bound

        provider = TestBedrockProvider._build_provider(mock_client)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "bedrock"
        assert exc_info.value.is_retryable is True

    @pytest.mark.asyncio
    async def test_timeout_triggers_retryable_error(self) -> None:
        """Verify Bedrock request timeout raises retryable LLMProviderError."""
        import asyncio

        mock_client = MagicMock()
        mock_bound = MagicMock()

        async def slow_ainvoke(*_args, **_kwargs):
            await asyncio.sleep(0.5)
            return _create_mock_aimessage("Too late")

        mock_bound.ainvoke = slow_ainvoke
        mock_client.bind.return_value = mock_bound

        provider = TestBedrockProvider._build_provider(mock_client)
        provider.timeout = 0.05
        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "bedrock"
        assert exc_info.value.is_retryable is True
        assert "timed out" in str(exc_info.value).lower()

    def test_bedrock_api_key_bearer_token_client_creation(self) -> None:
        """Verify BedrockProvider with bedrock_api_key creates unsigned client with Bearer token."""
        from botocore import UNSIGNED

        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="ap-south-2",
            aws_access_key_id="",
            aws_secret_access_key="",
            bedrock_api_key="bedrock-test-token",
        )
        assert provider._client is not None
        boto_client = provider._client.client
        assert boto_client.meta.config.signature_version is UNSIGNED

        dummy_request = MagicMock()
        dummy_request.headers = {}
        boto_client.meta.events.emit(
            "before-sign.bedrock-runtime.Converse",
            request=dummy_request,
        )
        assert dummy_request.headers.get("Authorization") == "Bearer bedrock-test-token"


class TestOpenAIProvider:
    """Test OpenAI provider implementation with mocked SDK."""

    @pytest.mark.asyncio
    async def test_successful_complete(self) -> None:
        """Verify successful OpenAI completion."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage("OpenAI analysis: resilient labor market.")
        )
        mock_client.bind.return_value = mock_bound

        provider = OpenAIProvider(
            api_key="sk-fake-openai-key",
            model="gpt-4o",
            client=mock_client,
        )

        resp = await provider.complete(
            [{"role": "user", "content": "Labor market analysis"}],
            temperature=0.2,
            max_tokens=250,
        )
        assert resp.provider == "openai"
        assert resp.model == "gpt-4o"
        assert resp.content == "OpenAI analysis: resilient labor market."
        assert resp.usage["total_tokens"] == 40
        mock_client.bind.assert_called_once_with(temperature=0.2, max_tokens=250)

    @pytest.mark.asyncio
    async def test_json_mode_passes_response_format(self) -> None:
        """Verify OpenAI json_mode passes response_format={'type': 'json_object'}."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage('{"employment_rate": 67.2}')
        )
        mock_client.bind.return_value = mock_bound

        provider = OpenAIProvider(
            api_key="sk-fake-openai-key",
            client=mock_client,
        )

        resp = await provider.complete([{"role": "user", "content": "Stats"}], json_mode=True)
        parsed = json.loads(resp.content)
        assert parsed["employment_rate"] == 67.2

        mock_client.bind.assert_called_once_with(
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

    @pytest.mark.asyncio
    async def test_retryable_rate_limit_error(self) -> None:
        """Verify OpenAI RateLimitError is flagged as is_retryable=True."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        err = Exception("RateLimitError: 429 requests limit exceeded")
        err.status_code = 429
        mock_bound.ainvoke = AsyncMock(side_effect=err)
        mock_client.bind.return_value = mock_bound

        provider = OpenAIProvider(api_key="sk-fake-key", client=mock_client)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "openai"
        assert exc_info.value.is_retryable is True


class TestAnthropicProvider:
    """Test Anthropic Claude provider implementation with mocked SDK."""

    @pytest.mark.asyncio
    async def test_successful_complete(self) -> None:
        """Verify successful Anthropic completion."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage("Claude evaluation of inflation dynamics.")
        )
        mock_client.bind.return_value = mock_bound

        provider = AnthropicProvider(
            api_key="sk-ant-fake-key",
            model="claude-3-5-sonnet-20241022",
            client=mock_client,
        )

        resp = await provider.complete(
            [{"role": "user", "content": "Inflation analysis"}],
            temperature=0.4,
            max_tokens=600,
        )
        assert resp.provider == "anthropic"
        assert resp.model == "claude-3-5-sonnet-20241022"
        assert resp.content == "Claude evaluation of inflation dynamics."
        assert resp.usage["total_tokens"] == 40
        mock_client.bind.assert_called_once_with(temperature=0.4, max_tokens=600)

    @pytest.mark.asyncio
    async def test_json_mode_and_health_check(self) -> None:
        """Verify Anthropic JSON mode instruction and health check."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=_create_mock_aimessage('{"cpi_core": 2.5, "cpi_headline": 2.7}')
        )
        mock_client.bind.return_value = mock_bound

        provider = AnthropicProvider(api_key="sk-ant-fake-key", client=mock_client)

        resp = await provider.complete([{"role": "user", "content": "Get CPI"}], json_mode=True)
        data = json.loads(resp.content)
        assert data["cpi_core"] == 2.5

        # Health check
        assert await provider.health_check() is True

        # Health check failure
        mock_bound.ainvoke = AsyncMock(side_effect=Exception("API status 529 Overloaded"))
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_retryable_overloaded_status_529(self) -> None:
        """Verify Anthropic status 529 overloaded error maps to is_retryable=True."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        overloaded_err = Exception("APIStatusError: Overloaded")
        overloaded_err.status_code = 529
        mock_bound.ainvoke = AsyncMock(side_effect=overloaded_err)
        mock_client.bind.return_value = mock_bound

        provider = AnthropicProvider(api_key="sk-ant-fake-key", client=mock_client)

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hi"}])

        assert exc_info.value.provider == "anthropic"
        assert exc_info.value.is_retryable is True
