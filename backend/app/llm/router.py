"""LLM routing layer with automatic retry, exponential backoff, and fallback failover."""

from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar
from typing import Any

from app.core.config import settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import AbstractLLMProvider, LLMResponse, validate_messages
from app.llm.bedrock_provider import BedrockProvider
from app.llm.exceptions import (
    AllProvidersFailedError,
    LLMProviderError,
    is_resource_exhausted_error,
    is_retryable_error,
)
from app.llm.gemini_provider import GeminiProvider
from app.llm.mock_provider import MockLLMProvider
from app.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Context variable tracking active query/analysis identifier
current_query_context: ContextVar[str | None] = ContextVar("current_query_context", default=None)
current_query_fallen_back: ContextVar[bool] = ContextVar("current_query_fallen_back", default=False)
current_query_gemini_exhausted: ContextVar[bool] = ContextVar(
    "current_query_gemini_exhausted", default=False
)


def _create_provider_by_name(provider_name: str, **kwargs: Any) -> AbstractLLMProvider:
    """Factory helper to instantiate provider instances by canonical identifier.

    Args:
        provider_name: Canonical name string ('gemini', 'bedrock', 'openai', 'anthropic', 'mock').
        **kwargs: Provider-specific configuration arguments.

    Returns:
        AbstractLLMProvider: Concrete provider implementation.

    Raises:
        ValueError: If provider_name is unrecognized.
    """
    clean_name = (provider_name or "").lower().strip()
    if clean_name == "gemini":
        return GeminiProvider(**kwargs)
    if clean_name == "bedrock":
        return BedrockProvider(**kwargs)
    if clean_name == "openai":
        return OpenAIProvider(**kwargs)
    if clean_name == "anthropic":
        return AnthropicProvider(**kwargs)
    if clean_name == "mock":
        return MockLLMProvider(**kwargs)
    raise ValueError(
        f"Unsupported LLM provider: '{provider_name}'. "
        "Supported providers: gemini, bedrock, openai, anthropic, mock."
    )


def _resolve_provider_name(provider: AbstractLLMProvider, fallback: str) -> str:
    """Extract canonical provider name string from an existing provider instance."""
    if hasattr(provider, "provider_name") and provider.provider_name:
        return str(provider.provider_name)
    if hasattr(provider, "provider") and provider.provider:
        return str(provider.provider)
    return fallback


class LLMRouter:
    """Intelligent LLM router coordinating primary and fallback provider resilience.

    Features:
        - Primary provider invocation with up to 3 retry attempts on transient errors.
        - Exponential backoff (1s, 2s, 4s scaled by backoff_factor).
        - Fail-fast on non-retryable errors (e.g. invalid auth, schema violations).
        - Automatic fallback failover to designated secondary provider.
        - Comprehensive exception tracking via AllProvidersFailedError when both fail.
        - Full Mock mode support via settings.MOCK_LLM.
        - Multi-provider health check probing with latency metrics.
    """

    def __init__(
        self,
        primary: AbstractLLMProvider | None = None,
        fallback: AbstractLLMProvider | None = None,
        *,
        primary_name: str | None = None,
        fallback_name: str | None = None,
        mock_mode: bool | None = None,
        llm_fallback: bool | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        """Initialize the LLMRouter.

        Args:
            primary: Optional pre-configured primary provider instance.
            fallback: Optional pre-configured fallback provider instance.
            primary_name: Override primary provider name (defaults to settings.PRIMARY_LLM_PROVIDER).
            fallback_name: Override fallback provider name (defaults to settings.FALLBACK_LLM_PROVIDER).
            mock_mode: Explicitly enable or disable mock provider mode (defaults to settings.MOCK_LLM).
            llm_fallback: Whether to attempt secondary provider when primary fails (defaults to settings.LLM_FALLBACK).
            max_retries: Maximum primary attempts on retryable errors (default: 3).
            backoff_factor: Multiplier for exponential backoff delays (default: 1.0, 0.0 in tests).
        """
        self.mock_mode = (
            mock_mode
            if mock_mode is not None
            else bool(getattr(settings, "mock_llm", False) or getattr(settings, "MOCK_LLM", False))
        )
        self.llm_fallback = (
            llm_fallback
            if llm_fallback is not None
            else bool(
                getattr(settings, "llm_fallback", False) or getattr(settings, "LLM_FALLBACK", False)
            )
        )
        self.max_retries = max(1, max_retries)
        self.backoff_factor = max(0.0, float(backoff_factor))

        configured_primary_name = (
            primary_name
            or getattr(settings, "primary_llm_provider", None)
            or getattr(settings, "PRIMARY_LLM_PROVIDER", "gemini")
        )
        configured_fallback_name = (
            fallback_name
            or getattr(settings, "fallback_llm_provider", None)
            or getattr(settings, "FALLBACK_LLM_PROVIDER", "bedrock")
        )

        if self.mock_mode:
            self.primary = primary or MockLLMProvider(model=f"mock-{configured_primary_name}")
            self.fallback = fallback or MockLLMProvider(model=f"mock-{configured_fallback_name}")
            self.primary_name = _resolve_provider_name(self.primary, "mock")
            self.fallback_name = _resolve_provider_name(self.fallback, "mock")
        else:
            self.primary = primary or _create_provider_by_name(configured_primary_name)
            self.fallback = fallback or _create_provider_by_name(configured_fallback_name)
            self.primary_name = _resolve_provider_name(self.primary, configured_primary_name)
            self.fallback_name = _resolve_provider_name(self.fallback, configured_fallback_name)

        # Track query IDs that have fallen back to secondary provider
        self._fallen_back_queries: set[str] = set()
        # Track query IDs where Gemini has exhausted quota/resources
        self._gemini_exhausted_queries: set[str] = set()
        self._gemini_resource_exhausted: bool = False
        self._gemini_exhausted_at: float = 0.0

        logger.info(
            "Initialized LLMRouter: primary=%s, fallback=%s, mock_mode=%s, llm_fallback=%s, max_retries=%d",
            self.primary_name,
            self.fallback_name,
            self.mock_mode,
            self.llm_fallback,
            self.max_retries,
        )

    def mark_gemini_exhausted(self, query_id: str | None = None) -> None:
        """Mark Gemini as resource-exhausted for the current query/request context."""
        qid = str(query_id) if query_id else current_query_context.get()
        if qid:
            self._gemini_exhausted_queries.add(qid)
        current_query_gemini_exhausted.set(True)
        self._gemini_resource_exhausted = True
        self._gemini_exhausted_at = time.time()
        logger.warning(
            "Gemini marked as resource exhausted for query '%s'. It will NOT be retried until a new request.",
            qid or "active",
        )

    def is_gemini_exhausted(self, query_id: str | None = None) -> bool:
        """Check whether Gemini has exhausted resources for the active query."""
        qid = str(query_id) if query_id else current_query_context.get()
        if qid and qid in self._gemini_exhausted_queries:
            return True
        return current_query_gemini_exhausted.get()

    def set_current_query(self, query_id: str | None) -> None:
        """Set the active query/analysis ID context for the current async execution."""
        qid = str(query_id) if query_id else None
        current_query_context.set(qid)
        if qid and qid in self._fallen_back_queries:
            current_query_fallen_back.set(True)
        else:
            current_query_fallen_back.set(False)

        # New query: only marked exhausted if explicitly in the set for this specific query
        if qid and qid in self._gemini_exhausted_queries:
            current_query_gemini_exhausted.set(True)
        else:
            current_query_gemini_exhausted.set(False)

    def mark_query_fallen_back(self, query_id: str | None = None) -> None:
        """Mark query as fallen back so all remaining requests in this query bypass primary."""
        qid = str(query_id) if query_id else current_query_context.get()
        if qid:
            self._fallen_back_queries.add(qid)
        current_query_fallen_back.set(True)
        logger.info(
            "Query '%s' marked as fallen back; all subsequent requests in this query will route directly to '%s'.",
            qid or "current",
            self.fallback_name,
        )

    def is_query_fallen_back(self, query_id: str | None = None) -> bool:
        """Check whether the active query has fallen back to secondary provider."""
        qid = str(query_id) if query_id else current_query_context.get()
        if qid and qid in self._fallen_back_queries:
            return True
        return current_query_fallen_back.get()

    def clear_current_query(self, query_id: str | None = None) -> None:
        """Clear query context upon completion so next user input query retries primary."""
        qid = str(query_id) if query_id else current_query_context.get()
        if qid:
            self._fallen_back_queries.discard(qid)
            self._gemini_exhausted_queries.discard(qid)
        current_query_context.set(None)
        current_query_fallen_back.set(False)
        current_query_gemini_exhausted.set(False)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        query_id: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute completion via primary provider with retry and automatic fallback failover.

        If the primary provider previously failed during this query execution, all subsequent
        requests in this query bypass the primary provider and invoke the fallback provider directly.
        Retry on primary is only restored on the next user input query.

        Args:
            messages: List of message dictionaries containing 'role' and 'content'.
            temperature: Sampling temperature (default: 0.7).
            max_tokens: Maximum tokens in generated completion (default: 1000).
            json_mode: Whether to enforce valid JSON output (default: False).
            query_id: Optional query identifier (defaults to current_query_context).
            **kwargs: Extra parameters passed to the active provider.

        Returns:
            LLMResponse: Successful completion from primary or fallback provider.

        Raises:
            ValueError: If messages list format is invalid.
            AllProvidersFailedError: If both primary and fallback attempts fail.
        """
        validate_messages(messages)

        effective_query_id = str(query_id) if query_id else current_query_context.get()

        # Check if this query has already fallen back to secondary provider
        if self.is_query_fallen_back(effective_query_id):
            if self.fallback_name == "gemini" and self.is_gemini_exhausted(effective_query_id):
                logger.error(
                    "Fallback provider 'gemini' resource is exhausted for query '%s'. Skipping without retrying.",
                    effective_query_id or "active",
                )
                raise AllProvidersFailedError(
                    f"Fallback provider ('{self.fallback_name}') quota is exhausted. Retry only on a new request.",
                    primary_error=None,
                    fallback_error=LLMProviderError(
                        "Gemini resource exhausted (429/quota).",
                        provider="gemini",
                        is_retryable=False,
                    ),
                    provider="router",
                )

            logger.info(
                "Query '%s' already fell back to secondary provider; skipping primary '%s' and directly using '%s'.",
                effective_query_id or "active",
                self.primary_name,
                self.fallback_name,
            )
            try:
                fallback_response = await self.fallback.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    **kwargs,
                )
                return fallback_response
            except Exception as fallback_exc:
                if self.fallback_name == "gemini" and is_resource_exhausted_error(fallback_exc):
                    self.mark_gemini_exhausted(effective_query_id)
                logger.error(
                    "Fallback provider '%s' failed on already-fallen-back query '%s': %s",
                    self.fallback_name,
                    effective_query_id,
                    fallback_exc,
                )
                raise AllProvidersFailedError(
                    f"Fallback provider ('{self.fallback_name}') failed to complete the request.",
                    primary_error=None,
                    fallback_error=fallback_exc,
                    provider="router",
                ) from fallback_exc

        last_primary_error: Exception | None = None
        logger.info("Using primary: %s", self.primary_name)

        # 1. Attempt primary provider with exponential retry on retryable errors
        for attempt in range(self.max_retries):
            try:
                response = await self.primary.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    **kwargs,
                )
                return response
            except Exception as exc:
                last_primary_error = exc
                is_exhausted = is_resource_exhausted_error(exc)
                retryable = False if is_exhausted else is_retryable_error(exc)
                logger.warning(
                    "Primary provider '%s' failed on attempt %d/%d (retryable=%s): %s",
                    self.primary_name,
                    attempt + 1,
                    self.max_retries,
                    retryable,
                    exc,
                )

                if is_exhausted:
                    if self.primary_name == "gemini":
                        self.mark_gemini_exhausted(effective_query_id)
                    logger.warning(
                        "Primary provider '%s' encountered resource exhaustion; stopping immediately without retry.",
                        self.primary_name,
                    )
                    break

                if not retryable:
                    logger.warning(
                        "Primary provider '%s' encountered non-retryable error; failing fast to fallback.",
                        self.primary_name,
                    )
                    break

                if attempt < self.max_retries - 1:
                    delay = (2**attempt) * self.backoff_factor
                    if delay > 0:
                        logger.info(
                            "Waiting %.2fs before retrying primary provider '%s'...",
                            delay,
                            self.primary_name,
                        )
                        await asyncio.sleep(delay)

        # 2. Primary failed all attempts or failed fast; transition to fallback provider
        if not self.llm_fallback:
            logger.warning(
                "Primary provider '%s' failed and fallback is disabled (LLM_FALLBACK=%s).",
                self.primary_name,
                self.llm_fallback,
            )
            raise AllProvidersFailedError(
                f"Primary provider ('{self.primary_name}') failed to complete the request and fallback is disabled (LLM_FALLBACK=false).",
                primary_error=last_primary_error,
                fallback_error=None,
                provider="router",
            )

        logger.warning("Primary failed, using fallback: %s", self.fallback_name)

        if self.fallback_name == "gemini" and self.is_gemini_exhausted(effective_query_id):
            logger.error(
                "Fallback provider 'gemini' resource is exhausted for query '%s'. Skipping without retrying.",
                effective_query_id or "active",
            )
            raise AllProvidersFailedError(
                f"Both primary ('{self.primary_name}') and fallback ('{self.fallback_name}') failed: "
                "fallback provider 'gemini' resource is exhausted (429/quota). Stopping without retry.",
                primary_error=last_primary_error,
                fallback_error=LLMProviderError(
                    "Gemini resource exhausted (429/quota).",
                    provider="gemini",
                    is_retryable=False,
                ),
                provider="router",
            )

        try:
            fallback_response = await self.fallback.complete(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                **kwargs,
            )
            # Mark this query as fallen back so subsequent LLM calls during this query skip primary
            self.mark_query_fallen_back(effective_query_id)
            return fallback_response
        except Exception as fallback_exc:
            if self.fallback_name == "gemini" and is_resource_exhausted_error(fallback_exc):
                self.mark_gemini_exhausted(effective_query_id)
                logger.error(
                    "Fallback provider 'gemini' encountered resource exhaustion (429/quota). "
                    "Stopping immediately without retry; will only retry on a new request when primary is not working."
                )
            else:
                logger.error(
                    "Fallback provider '%s' also failed: %s",
                    self.fallback_name,
                    fallback_exc,
                )
            raise AllProvidersFailedError(
                f"Both primary ('{self.primary_name}') and fallback ('{self.fallback_name}') "
                "providers failed to complete the request.",
                primary_error=last_primary_error,
                fallback_error=fallback_exc,
                provider="router",
            ) from fallback_exc

    async def check_health(self) -> dict[str, Any]:
        """Probe health status and latency for both primary and fallback providers.

        Returns:
            dict[str, Any]: Dictionary matching enriched health schema:
                {
                    "primary": {"provider": str, "status": "ok"|"error", "latency_ms": float},
                    "fallback": {"provider": str, "status": "ok"|"error", "latency_ms": float}
                }
        """
        # Primary provider probe
        p_start = time.perf_counter()
        try:
            p_ok = await self.primary.health_check()
        except Exception as exc:
            logger.warning("Primary health check probe failed with exception: %s", exc)
            p_ok = False
        p_latency = (time.perf_counter() - p_start) * 1000

        # Fallback provider probe
        f_start = time.perf_counter()
        try:
            f_ok = await self.fallback.health_check()
        except Exception as exc:
            logger.warning("Fallback health check probe failed with exception: %s", exc)
            f_ok = False
        f_latency = (time.perf_counter() - f_start) * 1000

        return {
            "primary": {
                "provider": self.primary_name,
                "status": "ok" if p_ok else "error",
                "latency_ms": round(p_latency, 2),
            },
            "fallback": {
                "provider": self.fallback_name,
                "status": "ok" if f_ok else "error",
                "latency_ms": round(f_latency, 2),
            },
        }

    async def health_check(self) -> bool:
        """Perform a quick boolean health check for router viability.

        Returns:
            bool: True if at least one configured provider (primary or fallback) is healthy.
        """
        status_dict = await self.check_health()
        return status_dict["primary"]["status"] == "ok" or status_dict["fallback"]["status"] == "ok"


_cached_router: LLMRouter | None = None
_cached_config_key: tuple[Any, ...] | None = None


def get_llm_router() -> LLMRouter:
    """FastAPI dependency providing a cached singleton instance of LLMRouter.

    Automatically refreshes when provider configuration in settings changes (e.g.,
    switching PRIMARY_LLM_PROVIDER between gemini and bedrock).

    Returns:
        LLMRouter: Initialized router configured according to application settings.
    """
    global _cached_router, _cached_config_key

    primary_name = getattr(settings, "primary_llm_provider", None) or getattr(
        settings, "PRIMARY_LLM_PROVIDER", "gemini"
    )
    fallback_name = getattr(settings, "fallback_llm_provider", None) or getattr(
        settings, "FALLBACK_LLM_PROVIDER", "bedrock"
    )
    mock_mode = bool(getattr(settings, "mock_llm", False) or getattr(settings, "MOCK_LLM", False))
    llm_fallback = bool(
        getattr(settings, "llm_fallback", False) or getattr(settings, "LLM_FALLBACK", False)
    )
    bedrock_model = getattr(settings, "bedrock_model_id", None) or getattr(
        settings, "BEDROCK_MODEL_ID", None
    )
    gemini_model = getattr(settings, "gemini_model", None) or getattr(
        settings, "GEMINI_MODEL", None
    )

    current_key = (
        primary_name,
        fallback_name,
        mock_mode,
        llm_fallback,
        bedrock_model,
        gemini_model,
    )

    if _cached_router is None or _cached_config_key != current_key:
        logger.info(
            "Configuring LLMRouter instance: primary=%s, fallback=%s, mock_mode=%s, llm_fallback=%s",
            primary_name,
            fallback_name,
            mock_mode,
            llm_fallback,
        )
        _cached_router = LLMRouter(
            primary_name=primary_name,
            fallback_name=fallback_name,
            mock_mode=mock_mode,
            llm_fallback=llm_fallback,
        )
        _cached_config_key = current_key

    return _cached_router


def reset_llm_router() -> None:
    """Clear cached singleton instance of LLMRouter (useful in testing suites)."""
    global _cached_router, _cached_config_key
    current_query_context.set(None)
    current_query_fallen_back.set(False)
    current_query_gemini_exhausted.set(False)
    _cached_router = None
    _cached_config_key = None
