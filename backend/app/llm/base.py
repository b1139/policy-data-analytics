"""Base classes and data models for LLM provider abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Standardized response container for all LLM provider completions.

    Attributes:
        content: The text or JSON string content produced by the model.
        model: Identifier of the model that generated the completion.
        provider: Provider identifier (e.g., 'gemini', 'bedrock', 'mock').
        usage: Token counts dict with keys 'input_tokens', 'output_tokens', 'total_tokens'.
        latency_ms: Execution duration in milliseconds.
    """

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the LLM response to a dictionary."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
        }


def validate_messages(messages: list[dict[str, Any]]) -> None:
    """Validate that messages conform to standard list of role/content dicts.

    Args:
        messages: List of message dictionaries.

    Raises:
        ValueError: If messages format is invalid.
    """
    if not isinstance(messages, list) or len(messages) == 0:
        raise ValueError("messages must be a non-empty list of message dictionaries.")

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError(f"Message at index {idx} must be a dictionary.")
        if "role" not in msg or "content" not in msg:
            raise ValueError(f"Message at index {idx} must contain both 'role' and 'content' keys.")
        if not isinstance(msg["role"], str) or not isinstance(msg["content"], str):
            raise ValueError(f"Message at index {idx} 'role' and 'content' must both be strings.")
        valid_roles = {"system", "user", "assistant", "tool"}
        if msg["role"] not in valid_roles:
            raise ValueError(
                f"Message at index {idx} has invalid role '{msg['role']}'. "
                f"Expected one of {sorted(valid_roles)}."
            )


class AbstractLLMProvider(ABC):
    """Abstract Base Class defining the contract for all LLM providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate an asynchronous completion from the LLM provider.

        Args:
            messages: List of message dicts: [{"role": "system"|"user"|"assistant", "content": str}]
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens in generated completion (default: 1000)
            json_mode: Whether to enforce valid JSON in response content (default: False)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse: Structured response model.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Perform a lightweight health check to determine provider availability.

        Returns:
            bool: True if provider is healthy and responsive, False otherwise.
        """
        ...
