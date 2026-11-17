"""Google Gemini LLM provider implementation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.llm.base import AbstractLLMProvider, LLMResponse, validate_messages
from app.llm.exceptions import LLMProviderError, is_resource_exhausted_error, is_retryable_error
from app.llm.utils import convert_messages_to_langchain, extract_token_usage, mask_key

logger = logging.getLogger(__name__)


class GeminiProvider(AbstractLLMProvider):
    """Google Gemini LLM provider implementation using ChatGoogleGenerativeAI."""

    _GENERATION_CONFIG_KEYS = {
        "temperature",
        "max_output_tokens",
        "top_p",
        "top_k",
        "candidate_count",
        "stop_sequences",
        "response_mime_type",
        "response_schema",
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        timeout: float | None = None,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Google Gemini provider.

        Args:
            api_key: Google Gemini API key. Defaults to settings.GEMINI_API_KEY.
            model: Gemini model identifier. Defaults to settings.GEMINI_MODEL.
            timeout: API request timeout in seconds. Defaults to settings.GEMINI_TIMEOUT_SECONDS.
            client: Pre-instantiated LangChain chat client for dependency injection / mocking.
            **kwargs: Extra parameters passed to ChatGoogleGenerativeAI if client is created.
        """
        self.provider_name = "gemini"
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = (
            model
            or getattr(settings, "gemini_model", None)
            or settings.GEMINI_MODEL
            or "gemini-1.5-flash"
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else (
                getattr(settings, "gemini_timeout_seconds", None)
                or getattr(settings, "GEMINI_TIMEOUT_SECONDS", None)
                or getattr(settings, "LLM_TIMEOUT_SECONDS", 30.0)
            )
        )
        self._extra_kwargs = kwargs
        self._injected_client = client is not None
        self._resource_exhausted = False
        self._resource_exhausted_at = 0.0

        logger.info(
            "Initializing GeminiProvider: model=%s, api_key=%s, timeout=%.1fs",
            self.model,
            mask_key(self.api_key),
            self.timeout,
        )

        chat_kwargs = dict(self._extra_kwargs)
        # Disable internal SDK retries on resource exhaustion / 429
        chat_kwargs.setdefault("retries", 0)

        if client is not None:
            self._client = client
        elif self.api_key:
            self._client = ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self.api_key,
                timeout=self.timeout,
                **chat_kwargs,
            )
        else:
            self._client = None

    def _get_client(
        self,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        extra_generation_config: dict[str, Any] | None = None,
    ) -> Any:
        """Obtain configured chat client or bound runnable with execution parameters."""
        if not self._injected_client and not self.api_key:
            raise LLMProviderError(
                "Gemini API key is not configured. Provide GEMINI_API_KEY or instantiate with api_key.",
                provider=self.provider_name,
                is_retryable=False,
            )

        if self._injected_client and self._client is not None:
            active_client = self._client
        elif self.api_key:
            if self._client is None:
                chat_kwargs = dict(self._extra_kwargs)
                chat_kwargs.setdefault("retries", 0)
                self._client = ChatGoogleGenerativeAI(
                    model=self.model,
                    google_api_key=self.api_key,
                    timeout=self.timeout,
                    **chat_kwargs,
                )
            active_client = self._client
        else:
            raise LLMProviderError(
                "Gemini API key is not configured. Provide GEMINI_API_KEY or instantiate with api_key.",
                provider=self.provider_name,
                is_retryable=False,
            )

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        if extra_generation_config:
            generation_config.update(extra_generation_config)

        if hasattr(active_client, "bind"):
            return active_client.bind(generation_config=generation_config)
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
        """Generate an asynchronous completion using Gemini.

        Args:
            messages: List of message dictionaries containing 'role' and 'content'.
            temperature: Sampling temperature (default 0.7).
            max_tokens: Maximum tokens in generated completion (default 1000).
            json_mode: Whether to enforce structured JSON output.
            **kwargs: Extra parameters passed to the invocation.

        Returns:
            LLMResponse containing response content, usage metrics, and latency.

        Raises:
            LLMProviderError: On any upstream API or invocation failure.
        """
        validate_messages(messages)
        lc_messages = convert_messages_to_langchain(
            messages,
            json_mode=json_mode,
            enforce_json_instruction=json_mode,
        )

        call_kwargs = dict(kwargs)
        call_timeout = float(call_kwargs.pop("timeout", None) or self.timeout)
        extra_gen_config: dict[str, Any] = {}
        if isinstance(call_kwargs.get("generation_config"), dict):
            extra_gen_config.update(call_kwargs.pop("generation_config"))
        for key in list(call_kwargs.keys()):
            if key in self._GENERATION_CONFIG_KEYS:
                extra_gen_config[key] = call_kwargs.pop(key)

        start_time = time.perf_counter()
        try:
            client = self._get_client(
                temperature,
                max_tokens,
                json_mode,
                extra_gen_config or None,
            )
            response = await asyncio.wait_for(
                client.ainvoke(lc_messages, **call_kwargs),
                timeout=call_timeout,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract content string
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
        except TimeoutError as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "LLM completion timed out: provider=%s, model=%s, timeout=%.1fs, latency_ms=%.2f",
                self.provider_name,
                self.model,
                call_timeout,
                latency_ms,
            )
            raise LLMProviderError(
                f"Gemini API request timed out after {call_timeout}s.",
                provider=self.provider_name,
                original_error=exc,
                is_retryable=True,
            ) from exc
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            is_exhausted = is_resource_exhausted_error(exc)
            retryable = False if is_exhausted else is_retryable_error(exc)

            if is_exhausted:
                self._resource_exhausted = True
                self._resource_exhausted_at = time.time()
                logger.error(
                    "Gemini resource exhausted (429/quota): provider=%s, model=%s, latency_ms=%.2f. "
                    "Stopping immediately without retry. Error: %s",
                    self.provider_name,
                    self.model,
                    latency_ms,
                    str(exc),
                )
                raise LLMProviderError(
                    f"Gemini API resource exhausted (quota exceeded): {exc}. Stopping immediately without retry.",
                    provider=self.provider_name,
                    original_error=exc,
                    is_retryable=False,
                ) from exc

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
                f"Gemini API completion error: {exc}",
                provider=self.provider_name,
                original_error=exc,
                is_retryable=retryable,
            ) from exc

    async def health_check(self) -> bool:
        """Perform a lightweight health check to determine Gemini availability."""
        # If resource exhausted recently (cooldown: 60s), avoid burning quota or hitting 429
        if getattr(self, "_resource_exhausted", False):
            elapsed = time.time() - getattr(self, "_resource_exhausted_at", 0.0)
            if elapsed < 60.0:
                logger.debug(
                    "Gemini health check skipped (recently resource exhausted: %.1fs ago).", elapsed
                )
                return False
            else:
                self._resource_exhausted = False
        try:
            res = await self.complete(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            return bool(res and res.content is not None)
        except Exception as exc:
            logger.warning("Gemini health check probe failed: %s", exc)
            return False
