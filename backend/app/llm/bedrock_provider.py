"""Amazon Bedrock LLM provider implementation."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotocoreConfig
from langchain_aws import ChatBedrockConverse

from app.core.config import settings
from app.llm.base import AbstractLLMProvider, LLMResponse, validate_messages
from app.llm.exceptions import LLMProviderError, is_retryable_error
from app.llm.utils import convert_messages_to_langchain, extract_token_usage, mask_key

logger = logging.getLogger(__name__)


class BedrockProvider(AbstractLLMProvider):
    """Amazon Bedrock LLM provider implementation using ChatBedrockConverse."""

    def __init__(
        self,
        model_id: str | None = None,
        *,
        region_name: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        bedrock_api_key: str | None = None,
        timeout: float | None = None,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Amazon Bedrock provider.

        Args:
            model_id: Bedrock model identifier. Defaults to settings.BEDROCK_MODEL_ID.
            region_name: AWS region name. Defaults to settings.AWS_REGION.
            aws_access_key_id: AWS Access Key ID. Defaults to settings.AWS_ACCESS_KEY_ID.
            aws_secret_access_key: AWS Secret Access Key. Defaults to settings.AWS_SECRET_ACCESS_KEY.
            bedrock_api_key: Optional Bedrock API key or Bearer token.
            timeout: API request timeout in seconds. Defaults to settings.BEDROCK_TIMEOUT_SECONDS.
            client: Pre-instantiated ChatBedrockConverse or compatible client.
            **kwargs: Extra parameters passed to ChatBedrockConverse.
        """
        self.provider_name = "bedrock"
        self.model = (
            model_id
            or getattr(settings, "bedrock_model_id", None)
            or settings.BEDROCK_MODEL_ID
            or "anthropic.claude-3-5-sonnet-20240620-v1:0"
        )
        self.region_name = (
            region_name or settings.AWS_REGION or settings.AWS_DEFAULT_REGION or "ap-south-2"
        )
        self.bedrock_api_key = (
            bedrock_api_key
            if bedrock_api_key is not None
            else (settings.BEDROCK_API_KEY or settings.AWS_BEARER_TOKEN_BEDROCK)
        )
        if bedrock_api_key is not None:
            self.aws_access_key_id = aws_access_key_id if aws_access_key_id is not None else ""
            self.aws_secret_access_key = aws_secret_access_key if aws_secret_access_key is not None else ""
        else:
            self.aws_access_key_id = (
                aws_access_key_id
                if aws_access_key_id is not None
                else settings.AWS_ACCESS_KEY_ID
            )
            self.aws_secret_access_key = (
                aws_secret_access_key
                if aws_secret_access_key is not None
                else settings.AWS_SECRET_ACCESS_KEY
            )
        self.timeout = float(
            timeout
            if timeout is not None
            else (
                getattr(settings, "bedrock_timeout_seconds", None)
                or getattr(settings, "BEDROCK_TIMEOUT_SECONDS", None)
                or getattr(settings, "LLM_TIMEOUT_SECONDS", 30.0)
            )
        )
        self._extra_kwargs = kwargs

        logger.info(
            "Initializing BedrockProvider: model=%s, region=%s, access_key=%s, api_key=%s, timeout=%.1fs",
            self.model,
            self.region_name,
            mask_key(self.aws_access_key_id),
            mask_key(self.bedrock_api_key),
            self.timeout,
        )

        if client is not None:
            self._client = client
        else:
            self._client = self._create_client()

    def _create_client(self) -> Any:
        """Instantiate ChatBedrockConverse with configured AWS credentials or Bedrock API key."""
        try:
            boto_client = None
            default_config = BotocoreConfig(
                connect_timeout=self.timeout,
                read_timeout=self.timeout,
            )
            has_iam_keys = bool(
                self.aws_access_key_id
                and self.aws_access_key_id.strip()
                and self.aws_secret_access_key
                and self.aws_secret_access_key.strip()
            )
            has_bedrock_key = bool(self.bedrock_api_key and self.bedrock_api_key.strip())

            if has_iam_keys:
                session = boto3.Session(
                    aws_access_key_id=self.aws_access_key_id.strip(),
                    aws_secret_access_key=self.aws_secret_access_key.strip(),
                    region_name=self.region_name,
                )
                boto_client = session.client(
                    "bedrock-runtime",
                    region_name=self.region_name,
                    config=default_config,
                )
            elif has_bedrock_key:
                raw_key = self.bedrock_api_key.strip().strip('"').strip("'")
                if ":" in raw_key and not raw_key.startswith("ABSK"):
                    access_key, secret_key = raw_key.split(":", 1)
                    session = boto3.Session(
                        aws_access_key_id=access_key.strip(),
                        aws_secret_access_key=secret_key.strip(),
                        region_name=self.region_name,
                    )
                    boto_client = session.client(
                        "bedrock-runtime",
                        region_name=self.region_name,
                        config=default_config,
                    )
                else:
                    token = raw_key.removeprefix("Bearer ").strip()
                    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token
                    if self.region_name in ("ap-south-2", "ap-southeast-3", "me-central-1"):
                        logger.warning(
                            "Region '%s' is an opt-in AWS region that may not support Bedrock API Key bearer authentication. "
                            "If you encounter HTTP 403 Authentication Failed, switch AWS_REGION to 'us-east-1', 'us-west-2', or 'ap-south-1'.",
                            self.region_name,
                        )
                    session = boto3.Session(region_name=self.region_name)
                    bearer_config = BotocoreConfig(
                        signature_version=UNSIGNED,
                        connect_timeout=self.timeout,
                        read_timeout=self.timeout,
                    )
                    boto_client = session.client(
                        "bedrock-runtime",
                        region_name=self.region_name,
                        config=bearer_config,
                    )

                    def _inject_bearer_token(request: Any, **_kwargs: Any) -> None:
                        request.headers["Authorization"] = f"Bearer {token}"

                    boto_client.meta.events.register(
                        "before-sign.bedrock-runtime.*",
                        _inject_bearer_token,
                    )
                    boto_client.meta.events.register(
                        "request-created.bedrock-runtime.*",
                        _inject_bearer_token,
                    )
            else:
                session = boto3.Session(region_name=self.region_name)
                if session.get_credentials() is None:
                    return None
                boto_client = session.client(
                    "bedrock-runtime",
                    region_name=self.region_name,
                    config=default_config,
                )

            return ChatBedrockConverse(
                model=self.model,
                client=boto_client,
                region_name=self.region_name,
                **self._extra_kwargs,
            )
        except Exception as exc:
            logger.warning(
                "Bedrock client initialization deferred or encountered warning: %s",
                exc,
            )
            return None

    def _get_client(self, temperature: float, max_tokens: int) -> Any:
        """Obtain active client or bound runnable with call options."""
        client = self._client
        if client is None:
            client = self._create_client()
            self._client = client

        if client is None:
            raise LLMProviderError(
                "Amazon Bedrock client could not be initialized. Check AWS credentials or region configuration.",
                provider=self.provider_name,
                is_retryable=False,
            )

        bind_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if hasattr(client, "bind"):
            return client.bind(**bind_kwargs)
        return client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate an asynchronous completion using Amazon Bedrock.

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

        call_kwargs = dict(kwargs)
        call_timeout = float(call_kwargs.pop("timeout", None) or self.timeout)

        start_time = time.perf_counter()
        try:
            client = self._get_client(temperature, max_tokens)
            response = await asyncio.wait_for(
                client.ainvoke(lc_messages, **call_kwargs),
                timeout=call_timeout,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract content text defensively
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
                f"Amazon Bedrock API request timed out after {call_timeout}s.",
                provider=self.provider_name,
                original_error=exc,
                is_retryable=True,
            ) from exc
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            retryable = is_retryable_error(exc)
            err_msg = str(exc)
            logger.error(
                "LLM completion failed: provider=%s, model=%s, latency_ms=%.2f, is_retryable=%s, error=%s",
                self.provider_name,
                self.model,
                latency_ms,
                retryable,
                err_msg,
            )
            if isinstance(exc, LLMProviderError):
                raise
            if "Error 002" in err_msg or "Access to Bedrock models is not allowed" in err_msg:
                raise LLMProviderError(
                    f"AWS Bedrock account access restriction: {err_msg}. "
                    "Your AWS account has not requested or been granted model access in the AWS Bedrock Console, "
                    "or this account has an active AWS account-level restriction. "
                    "Please check AWS Console -> Amazon Bedrock -> Model access.",
                    provider=self.provider_name,
                    original_error=exc,
                    is_retryable=False,
                ) from exc
            if (
                "Authentication failed: Please make sure your API Key is valid" in err_msg
                and self.region_name == "ap-south-2"
            ):
                raise LLMProviderError(
                    f"AWS Bedrock API Key authentication failed in region '{self.region_name}'. "
                    "Bedrock API keys (bearer tokens) are not supported in opt-in region 'ap-south-2'. "
                    "Please set AWS_REGION to 'us-east-1', 'us-west-2', or 'ap-south-1'.",
                    provider=self.provider_name,
                    original_error=exc,
                    is_retryable=False,
                ) from exc
            raise LLMProviderError(
                f"Bedrock API completion error: {exc}",
                provider=self.provider_name,
                original_error=exc,
                is_retryable=retryable,
            ) from exc

    async def health_check(self) -> bool:
        """Perform a lightweight health check to determine Bedrock availability."""
        try:
            res = await self.complete(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            return bool(res and res.content is not None)
        except Exception as exc:
            logger.warning("Bedrock health check probe failed: %s", exc)
            return False
