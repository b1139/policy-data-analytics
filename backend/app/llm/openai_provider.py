"""OpenAI LLM provider implementation."""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.llm.base import AbstractLLMProvider, LLMResponse, validate_messages
from app.llm.exceptions import LLMProviderError, is_retryable_error
from app.llm.utils import convert_messages_to_langchain, extract_token_usage, mask_key

logger = logging.getLogger(__name__)


class OpenAIProvider(AbstractLLMProvider):
    """OpenAI LLM provider implementation using ChatOpenAI."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key. Defaults to settings.OPENAI_API_KEY.
            model: Model identifier. Defaults to settings.openai_model or settings.OPENAI_MODEL ('gpt-4o').
            client: Pre-instantiated LangChain ChatOpenAI client for testing / injection.
            **kwargs: Extra arguments passed to ChatOpenAI constructor.
        """
        self.provider_name = "openai"
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = (
            model
            or getattr(settings, "openai_model", None)
            or getattr(settings, "OPENAI_MODEL", None)
            or "gpt-4o"
        )
        self._extra_kwargs = kwargs

        logger.info(
            "Initializing OpenAIProvider: model=%s, api_key=%s",
            self.model,
            mask_key(self.api_key),
        )

        if client is not None:
            self._client = client
        elif self.api_key:
            self._client = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                **self._extra_kwargs,
            )
        else:
            self._client = None

    def _get_client(self, temperature: float, max_tokens: int, json_mode: bool) -> Any:
        """Obtain active client or bound runnable with call options."""
        if self._client is not None:
            active_client = self._client
        elif self.api_key:
            active_client = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                **self._extra_kwargs,
            )
            self._client = active_client
        else:
            raise LLMProviderError(
                "OpenAI API key is not configured. Provide OPENAI_API_KEY or instantiate with api_key.",
                provider=self.provider_name,
                is_retryable=False,
            )

        bind_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            bind_kwargs["response_format"] = {"type": "json_object"}

        if hasattr(active_client, "bind"):
            return active_client.bind(**bind_kwargs)
        return active_client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate an asynchronous completion using OpenAI.

        Args:
            messages: List of message dictionaries containing 'role' and 'content'.
            temperature: Sampling temperature (default 0.7).
            max_tokens: Maximum tokens in generated completion (default 1000).
            json_mode: Whether to enforce valid JSON format.
            **kwargs: Extra parameters passed to the invocation.

        Returns:
            LLMResponse containing response content, usage metrics, and latency.

        Raises:
            LLMProviderError: On any API or invocation failure.
        """
        validate_messages(messages)
        lc_messages = convert_messages_to_langchain(
            messages,
            json_mode=json_mode,
            enforce_json_instruction=json_mode,
        )

        start_time = time.perf_counter()
        try:
            client = self._get_client(temperature, max_tokens, json_mode)
            response = await client.ainvoke(lc_messages, **kwargs)
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Content string extraction
            raw_content = getattr(response, "content", "")
            if isinstance(raw_content, str):
                content = raw_content
            elif isinstance(raw_content, list):
                parts = []
                for item in raw_content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        parts.append(str(item["text"]))
                    elif hasattr(item, "text"):
                        parts.append(str(item.text))
                content = "".join(parts)
            else:
                content = str(raw_content)

            usage = extract_token_usage(response)

            logger.info(
                "LLM completion succeeded: provider=%s, model=%s, input_tokens=%d, "
                "output_tokens=%d, total_tokens=%d, latency_ms=%.2f",
                self.provider_name,
                self.model,
                usage["input_tokens"],
                usage["output_tokens"],
                usage["total_tokens"],
                latency_ms,
            )

            return LLMResponse(
                content=content,
                model=self.model,
                provider=self.provider_name,
                usage=usage,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            retryable = is_retryable_error(exc)
            logger.error(
                "LLM completion failed: provider=%s, model=%s, latency_ms=%.2f, is_retryable=%s, error=%s",
                self.provider_name,
                self.model,
                latency_ms,
                retryable,
                str(exc),
            )
            if isinstance(exc, LLMProviderError):
                raise
            raise LLMProviderError(
                f"OpenAI API completion error: {exc}",
                provider=self.provider_name,
                original_error=exc,
                is_retryable=retryable,
            ) from exc

    async def health_check(self) -> bool:
        """Perform a lightweight health check to determine OpenAI availability."""
        try:
            res = await self.complete(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            return bool(res and res.content is not None)
        except Exception as exc:
            logger.warning("OpenAI health check probe failed: %s", exc)
            return False
