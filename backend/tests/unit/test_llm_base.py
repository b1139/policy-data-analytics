"""Unit tests for LLM provider abstraction layer and MockLLMProvider."""

import json
from typing import Any

import pytest

from app.llm import AbstractLLMProvider, LLMResponse, MockLLMProvider, validate_messages


class TestLLMResponse:
    """Test LLMResponse data container."""

    def test_default_values(self) -> None:
        """Verify default usage and latency in LLMResponse."""
        resp = LLMResponse(
            content="Test content",
            model="test-model",
            provider="test-provider",
        )
        assert resp.content == "Test content"
        assert resp.model == "test-model"
        assert resp.provider == "test-provider"
        assert resp.usage == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        assert resp.latency_ms == 0.0

    def test_custom_values_and_to_dict(self) -> None:
        """Verify custom values and dictionary serialization."""
        usage = {"input_tokens": 120, "output_tokens": 80, "total_tokens": 200}
        resp = LLMResponse(
            content='{"key": "val"}',
            model="claude-3-haiku",
            provider="bedrock",
            usage=usage,
            latency_ms=142.5,
        )
        data = resp.to_dict()
        assert data == {
            "content": '{"key": "val"}',
            "model": "claude-3-haiku",
            "provider": "bedrock",
            "usage": usage,
            "latency_ms": 142.5,
        }


class TestAbstractLLMProvider:
    """Test AbstractLLMProvider interface contracts."""

    def test_cannot_instantiate_abc(self) -> None:
        """Ensure AbstractLLMProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AbstractLLMProvider()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_concrete_implementation(self) -> None:
        """Ensure properly implemented subclasses satisfy ABC contracts."""

        class ConcreteProvider(AbstractLLMProvider):
            async def complete(
                self,
                messages: list[dict[str, Any]],
                *,
                temperature: float = 0.7,
                max_tokens: int = 1000,
                json_mode: bool = False,
                **kwargs: Any,
            ) -> LLMResponse:
                _ = (messages, temperature, max_tokens, json_mode, kwargs)
                return LLMResponse(
                    content="Hello world",
                    model="concrete-model",
                    provider="concrete",
                )

            async def health_check(self) -> bool:
                return True

        provider = ConcreteProvider()
        health = await provider.health_check()
        assert health is True

        resp = await provider.complete([{"role": "user", "content": "Hi"}])
        assert resp.content == "Hello world"
        assert resp.model == "concrete-model"
        assert resp.provider == "concrete"


class TestValidateMessages:
    """Test message structure validation."""

    def test_valid_messages(self) -> None:
        """Valid system, user, and assistant messages should pass without error."""
        messages = [
            {"role": "system", "content": "You are a helpful analyst."},
            {"role": "user", "content": "What is the unemployment rate?"},
            {"role": "assistant", "content": "The resident rate is 2.7%."},
            {"role": "tool", "content": '{"result": "ok"}'},
        ]
        validate_messages(messages)

    def test_empty_or_non_list(self) -> None:
        """Empty or non-list message structures must raise ValueError."""
        with pytest.raises(ValueError, match="non-empty list"):
            validate_messages([])

        with pytest.raises(ValueError, match="non-empty list"):
            validate_messages("not a list")  # type: ignore[arg-type]

    def test_invalid_element_type(self) -> None:
        """Non-dict element must raise ValueError."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            validate_messages(["not a dict"])  # type: ignore[list-item]

    def test_missing_role_or_content(self) -> None:
        """Dictionaries missing role or content must raise ValueError."""
        with pytest.raises(ValueError, match="must contain both 'role' and 'content'"):
            validate_messages([{"role": "user"}])

        with pytest.raises(ValueError, match="must contain both 'role' and 'content'"):
            validate_messages([{"content": "hello"}])

    def test_invalid_role(self) -> None:
        """Invalid roles must raise ValueError."""
        with pytest.raises(ValueError, match="invalid role"):
            validate_messages([{"role": "superadmin", "content": "do something"}])

    def test_non_string_content(self) -> None:
        """Non-string role or content must raise ValueError."""
        with pytest.raises(ValueError, match="must both be strings"):
            validate_messages([{"role": "user", "content": 12345}])


class TestMockLLMProvider:
    """Test MockLLMProvider behavior, keywords, json_mode, and latency."""

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """MockLLMProvider health_check must always return True."""
        mock = MockLLMProvider()
        assert await mock.health_check() is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_topic_fragment",
        [
            ("What are the latest employment numbers?", "resident employment rate"),
            (
                "Explain the foreign workforce policies and work permit quotas",
                "foreign workforce policy",
            ),
            ("What is Singapore's recent GDP growth?", "Gross Domestic Product"),
            ("How has headline inflation and CPI trended?", "Consumer Price Index"),
            ("What policy recommendations do you propose?", "policy recommendations"),
            ("Provide an overview of general matters", "Policy data analytics evaluation"),
        ],
    )
    async def test_keyword_routing_text_mode(
        self, query: str, expected_topic_fragment: str
    ) -> None:
        """Ensure standard query keywords return appropriate domain text responses."""
        mock = MockLLMProvider()
        resp = await mock.complete([{"role": "user", "content": query}])

        assert resp.provider == "mock"
        assert resp.model == "mock-model"
        assert expected_topic_fragment in resp.content
        assert resp.usage["input_tokens"] > 0
        assert resp.usage["output_tokens"] > 0
        assert (
            resp.usage["total_tokens"] == resp.usage["input_tokens"] + resp.usage["output_tokens"]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_topic",
        [
            ("foreign workforce stats", "foreign_workforce"),
            ("employment numbers", "employment"),
            ("GDP expansion", "gdp"),
            ("inflation rate trends", "inflation"),
            ("give me policy recommendations", "policy_recommendations"),
            ("random unmapped query", "general_policy_analytics"),
        ],
    )
    async def test_json_mode_returns_valid_json(self, query: str, expected_topic: str) -> None:
        """Ensure json_mode=True returns valid parseable JSON with expected topic."""
        mock = MockLLMProvider(model="mock-json-v1")
        resp = await mock.complete(
            [{"role": "user", "content": query}],
            json_mode=True,
        )

        assert resp.model == "mock-json-v1"
        payload = json.loads(resp.content)
        assert isinstance(payload, dict)
        assert payload.get("topic") == expected_topic
        assert payload.get("status") == "success"

    @pytest.mark.asyncio
    async def test_mock_latency_simulation(self) -> None:
        """Ensure mock_latency_ms simulates realistic execution latency."""
        mock = MockLLMProvider(mock_latency_ms=30.0)
        resp = await mock.complete([{"role": "user", "content": "employment"}])
        assert resp.latency_ms >= 25.0

    @pytest.mark.asyncio
    async def test_custom_responses(self) -> None:
        """Verify custom keyword responses map properly in text and json mode."""
        custom_mapping = {
            "custom_metric": "This is a custom metric evaluation.",
            "structured_metric": {"score": 99, "flag": True},
        }
        mock = MockLLMProvider(custom_responses=custom_mapping)

        # Test string custom response
        resp_text = await mock.complete([{"role": "user", "content": "analyze custom_metric"}])
        assert "This is a custom metric evaluation." in resp_text.content

        # Test structured custom response in json_mode
        resp_json = await mock.complete(
            [{"role": "user", "content": "show structured_metric"}],
            json_mode=True,
        )
        parsed = json.loads(resp_json.content)
        assert parsed.get("score") == 99
        assert parsed.get("flag") is True
