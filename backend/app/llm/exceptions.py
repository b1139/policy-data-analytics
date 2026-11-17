"""Exceptions and retry classification for LLM providers."""

from __future__ import annotations

import asyncio
from typing import Any


class LLMProviderError(Exception):
    """Custom exception raised when an LLM provider encounters an error.

    Attributes:
        message: Human-readable error message.
        provider: Provider identifier (e.g., 'gemini', 'bedrock', 'openai', 'anthropic').
        original_error: The underlying original exception if available.
        is_retryable: True if the failure is transient (e.g., rate limit, timeout, 5xx),
            suggesting a retry or fallback may succeed.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        original_error: Exception | None = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.original_error = original_error
        self.is_retryable = is_retryable

    @property
    def user_friendly_message(self) -> str:
        """User-friendly status message free of internal stack traces."""
        msg = (self.message or "").lower()
        if "rate limit" in msg or "429" in msg or "quota" in msg or "resource exhausted" in msg:
            return f"The AI service ({self.provider}) is currently experiencing high demand or rate limits. Please try again shortly."
        if "timeout" in msg or "timed out" in msg or "504" in msg:
            return f"The AI service ({self.provider}) timed out while processing the request. Please retry."
        if "auth" in msg or "key" in msg or "credential" in msg or "401" in msg or "403" in msg:
            return f"The AI provider ({self.provider}) authentication service is temporarily unavailable."
        return f"AI provider ({self.provider}) was unable to complete the request. Please try again."

    def __str__(self) -> str:
        retry_flag = "retryable" if self.is_retryable else "non-retryable"
        orig = (
            f" (caused by {type(self.original_error).__name__}: {self.original_error})"
            if self.original_error
            else ""
        )
        return f"[{self.provider}] [{retry_flag}] {self.message}{orig}"


class AllProvidersFailedError(LLMProviderError):
    """Exception raised when all configured LLM providers fail.

    Attributes:
        message: Descriptive error message.
        primary_error: The exception encountered by the primary provider.
        fallback_error: The exception encountered by the fallback provider.
        provider: Provider identifier (default 'router').
    """

    def __init__(
        self,
        message: str = "All configured LLM providers failed to complete the request.",
        *,
        primary_error: Exception | None = None,
        fallback_error: Exception | None = None,
        provider: str = "router",
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            original_error=fallback_error or primary_error,
            is_retryable=False,
        )
        self.primary_error = primary_error
        self.fallback_error = fallback_error

    @property
    def user_friendly_message(self) -> str:
        """User-friendly status message indicating fallback and outage status."""
        return (
            "AI service temporarily unavailable: both primary and fallback language models "
            "could not be reached. Please try re-running the analysis or check provider status."
        )

    def __str__(self) -> str:
        p_desc = (
            f"{type(self.primary_error).__name__}: {self.primary_error}"
            if self.primary_error
            else "None"
        )
        f_desc = (
            f"{type(self.fallback_error).__name__}: {self.fallback_error}"
            if self.fallback_error
            else "None"
        )
        return (
            f"[{self.provider}] {self.message} (primary_error: {p_desc}, fallback_error: {f_desc})"
        )


def format_user_friendly_error(exc: Exception | str | None) -> str:
    """Format any exception or error string into a clean, user-friendly status message.

    Eliminates Python stack traces, file paths, line numbers, and internal dumps,
    presenting a readable, actionable status message to the user.

    Args:
        exc: Exception instance or raw error string.

    Returns:
        str: User-friendly error message.
    """
    if exc is None:
        return "An unexpected error occurred during execution."

    if hasattr(exc, "user_friendly_message") and exc.user_friendly_message:
        return str(exc.user_friendly_message)

    raw_text = str(exc)

    # If it's a known AllProvidersFailedError string
    if "All configured LLM providers failed" in raw_text or "AllProvidersFailedError" in raw_text:
        return (
            "AI service temporarily unavailable: both primary and backup language models "
            "could not be reached. Please try re-running the analysis."
        )

    # Check for rate limit or quota
    lower = raw_text.lower()
    if "rate limit" in lower or "429" in lower or "resource exhausted" in lower or "quota exceeded" in lower:
        return "The AI service is currently busy or rate-limited. Please retry your query in a few moments."

    # Check for timeout / network issues
    if "timed out" in lower or "timeout" in lower or "connection refused" in lower or "504" in lower or "502" in lower:
        return "Service connection timed out while processing your request. Please try re-running."

    # Check for extraction failure
    if "extraction failed" in lower or "no datasets retrieved" in lower or "no matching datasets" in lower:
        # Extract title or dataset if present
        if "for '" in raw_text:
            try:
                ds_part = raw_text.split("for '")[1].split("'")[0]
                return f"Data extraction could not retrieve official records for '{ds_part}'. You can re-run or resolve using AI."
            except Exception:
                pass
        return "Data extraction could not retrieve official records for the requested parameters. You can re-run or use AI to resolve."

    # Check for authorization / API key
    if "api key" in lower or "unauthorized" in lower or "401" in lower or "forbidden" in lower or "403" in lower:
        return "AI service configuration or authentication is temporarily unavailable."

    # Remove stack trace if present
    if "Traceback (most recent call last):" in raw_text:
        # Extract the final exception message line
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        last_line = lines[-1] if lines else "Analysis execution failed."
        # Clean up common exception prefixes like "ValueError: "
        if ": " in last_line:
            last_line = last_line.split(": ", 1)[1]
        return f"Analysis execution encountered an issue: {last_line}"

    # General cleanup: truncate if abnormally long and remove newline dumps
    cleaned = raw_text.replace("\n", " ").strip()
    if len(cleaned) > 200:
        cleaned = cleaned[:197] + "..."
    return cleaned


def is_resource_exhausted_error(exc: Exception | None) -> bool:
    """Determine whether an exception represents resource exhaustion or quota limits on Gemini.

    Resource exhaustion (e.g. Google Gemini 429 ResourceExhausted, daily/minute quota exceeded)
    must stop immediately and NOT be retried in a loop, as quota cannot be resolved by immediate
    retries and should only be attempted on a new request when primary is unavailable.
    """
    if exc is None:
        return False

    provider = getattr(exc, "provider", "")
    orig = getattr(exc, "original_error", None)

    type_names = [type(exc).__name__]
    if orig is not None:
        type_names.append(type(orig).__name__)

    if any("resourceexhausted" in tn.lower() for tn in type_names):
        return True

    msg = (str(exc) + (" " + str(orig) if orig else "")).lower()

    # Check for Gemini provider specifically or Google quota messages
    is_gemini = provider == "gemini" or "gemini" in msg or "generativeai" in msg or "google" in msg
    if is_gemini and any(k in msg for k in ("resource exhausted", "quota exceeded", "check quota", "429", "rate limit")):
        return True

    exhaustion_keywords = (
        "resource exhausted",
        "resourceexhausted",
        "quota exceeded",
        "check quota",
        "resource_exhausted",
        "free tier limit",
    )
    return any(k in msg for k in exhaustion_keywords)


def is_retryable_error(exc: Exception | None) -> bool:
    """Determine whether an exception represents a transient/retryable condition.

    Flags network timeouts, connection resets, and overloaded server errors
    as retryable across Google Gemini, Amazon Bedrock, OpenAI, Anthropic, and HTTP layers.
    Note: Resource exhaustion on Gemini is explicitly NOT retryable and stops immediately.

    Args:
        exc: Exception instance to evaluate.

    Returns:
        bool: True if retryable, False otherwise.
    """
    if exc is None:
        return False

    # Explicit is_retryable flag on custom LLMProviderError
    if hasattr(exc, "is_retryable") and isinstance(exc.is_retryable, bool):
        return exc.is_retryable

    # Gemini resource exhaustion must never be retried in a rapid loop
    if is_resource_exhausted_error(exc):
        return False

    # Standard Python / asyncio transient errors
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return True

    # Error type name matching (covers dynamic / optional SDK imports)
    type_name = type(exc).__name__
    retryable_type_substrings = (
        "RateLimit",
        "Timeout",
        "TimedOut",
        "ConnectionError",
        "ConnectionReset",
        "Overloaded",
        "ServiceUnavailable",
        "DeadlineExceeded",
        "TooManyRequests",
        "Throttling",
        "InternalServerError",
    )
    if any(sub in type_name for sub in retryable_type_substrings):
        return True

    # Inspect HTTP status codes if available on the exception
    status_code: int | None = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "status", None)
    if status_code is None and hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status_code = exc.response.status_code

    if status_code in {429, 500, 502, 503, 504, 529}:
        return True

    # AWS / Boto3 / Botocore error codes inspection
    response_dict: Any = getattr(exc, "response", None)
    if isinstance(response_dict, dict):
        error_info = response_dict.get("Error", {})
        code = str(error_info.get("Code", ""))
        retryable_aws_codes = {
            "ThrottlingException",
            "ProvisionedThroughputExceededException",
            "ModelTimeoutException",
            "ServiceUnavailableException",
            "InternalServerException",
            "RequestTimeout",
            "TooManyRequestsException",
        }
        if code in retryable_aws_codes:
            return True

    # Message string inspection heuristics
    msg = str(exc).lower()
    retryable_keywords = (
        "rate limit",
        "rate_limit",
        "ratelimit",
        "too many requests",
        "429",
        "529",
        "overloaded",
        "timed out",
        "timeout",
        "connection refused",
        "connection reset",
        "temporarily unavailable",
        "service unavailable",
        "throttled",
    )
    return any(keyword in msg for keyword in retryable_keywords)
