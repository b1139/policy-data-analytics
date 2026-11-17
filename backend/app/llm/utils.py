"""Utility functions for LLM providers (masking, token extraction, message conversion)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def mask_key(key: str | None, visible_prefix_len: int = 4) -> str:
    """Mask an API key or sensitive secret for safe logging.

    Example:
        'AIzaSyD123456789' -> 'AIza...****'
        'sk-ant-api03-xxx' -> 'sk-a...****'
        'AKIAIOSFODNN7EXAMPLE' -> 'AKIA...****'

    Args:
        key: The raw secret string.
        visible_prefix_len: Number of characters from the prefix to preserve.

    Returns:
        Safe masked representation string.
    """
    if not key:
        return "[NOT_SET]"
    clean_key = str(key).strip()
    if len(clean_key) <= visible_prefix_len:
        return "****"
    prefix = clean_key[:visible_prefix_len]
    return f"{prefix}...****"


def extract_token_usage(response: Any) -> dict[str, int]:
    """Extract token usage metrics from a LangChain response or dict.

    Extracts input_tokens, output_tokens, and total_tokens defensively across
    different LangChain provider implementations and versions.

    Args:
        response: AIMessage or response object from a model invocation.

    Returns:
        dict with 'input_tokens', 'output_tokens', 'total_tokens'.
    """
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 1. LangChain 0.2+ standard usage_metadata attribute
    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        usage["input_tokens"] = int(usage_metadata.get("input_tokens") or 0)
        usage["output_tokens"] = int(usage_metadata.get("output_tokens") or 0)
        usage["total_tokens"] = int(
            usage_metadata.get("total_tokens") or (usage["input_tokens"] + usage["output_tokens"])
        )
        return usage

    # 2. Check response_metadata (token_usage, usage, or direct keys)
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_data = (
            response_metadata.get("token_usage")
            or response_metadata.get("usage")
            or response_metadata
        )
        if isinstance(token_data, dict):
            in_tokens = int(
                token_data.get("prompt_tokens")
                or token_data.get("input_tokens")
                or token_data.get("input_token_count")
                or 0
            )
            out_tokens = int(
                token_data.get("completion_tokens")
                or token_data.get("output_tokens")
                or token_data.get("output_token_count")
                or 0
            )
            tot_tokens = int(
                token_data.get("total_tokens")
                or token_data.get("total_token_count")
                or (in_tokens + out_tokens)
            )
            usage["input_tokens"] = in_tokens
            usage["output_tokens"] = out_tokens
            usage["total_tokens"] = tot_tokens
            return usage

    # 3. Direct dictionary format
    if isinstance(response, dict):
        u = response.get("usage") or response.get("token_usage") or {}
        if isinstance(u, dict):
            usage["input_tokens"] = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
            usage["output_tokens"] = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
            usage["total_tokens"] = int(
                u.get("total_tokens") or (usage["input_tokens"] + usage["output_tokens"])
            )

    return usage


def convert_messages_to_langchain(
    messages: list[dict[str, Any]],
    *,
    json_mode: bool = False,
    enforce_json_instruction: bool = False,
) -> list[BaseMessage]:
    """Convert platform role/content dictionaries into LangChain BaseMessage objects.

    If json_mode is True and enforce_json_instruction is True, ensures that
    a system instruction directing JSON output is present.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        json_mode: Whether JSON response mode is enabled.
        enforce_json_instruction: Whether to explicitly append/prepend JSON instruction.

    Returns:
        List of LangChain BaseMessage objects (SystemMessage, HumanMessage, AIMessage).
    """
    lc_messages: list[BaseMessage] = []
    has_system = False
    json_instruction = "Respond with valid JSON only."

    for msg in messages:
        role = str(msg.get("role", "user")).lower()
        content = str(msg.get("content", ""))

        if role == "system":
            has_system = True
            if json_mode and enforce_json_instruction and "json" not in content.lower():
                content = f"{content}\n\n{json_instruction}"
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    if json_mode and enforce_json_instruction and not has_system:
        # Prepend system message enforcing JSON format
        lc_messages.insert(
            0, SystemMessage(content=f"You are a helpful assistant. {json_instruction}")
        )

    return lc_messages
