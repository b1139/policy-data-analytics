"""Redis and in-memory Pub/Sub event broker for real-time WebSocket streaming."""

import asyncio
import contextlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from app.core.redis import check_redis_health, get_redis_client
from app.schemas.websocket import WSMessageType

logger = logging.getLogger(__name__)

CHANNEL_CLOSE_SENTINEL = "__CHANNEL_CLOSED__"


class InMemoryPubSub:
    """In-memory pub/sub broker providing local fallback when Redis is offline.

    Thread-safe and cross-event-loop safe for seamless testing with TestClient and ASGI.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]]] = (
            defaultdict(set)
        )
        self._lock = threading.Lock()

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message string to all active subscriber queues for channel.

        Args:
            channel: Topic channel identifier.
            message: Formatted JSON payload string.

        Returns:
            int: Number of subscriber queues that received the message.
        """
        with self._lock:
            subscribers = list(self._subscribers.get(channel, set()))

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for loop, queue in subscribers:
            if loop.is_closed():
                continue
            if current_loop is loop:
                queue.put_nowait(message)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, message)

        return len(subscribers)

    async def subscribe(self, channel: str) -> asyncio.Queue[str]:
        """Register a subscriber queue for the specified channel.

        Args:
            channel: Topic channel identifier.

        Returns:
            asyncio.Queue[str]: Queue receiving message strings.
        """
        queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[channel].add((loop, queue))
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[str]) -> None:
        """Deregister an active subscriber queue.

        Args:
            channel: Topic channel identifier.
            queue: The subscriber queue to remove.
        """
        with self._lock:
            if channel in self._subscribers:
                self._subscribers[channel] = {
                    (loop, q) for (loop, q) in self._subscribers[channel] if q is not queue
                }
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

    async def close_channel(self, channel: str) -> None:
        """Send termination sentinel to all subscribers on channel.

        Args:
            channel: Topic channel identifier to close.
        """
        with self._lock:
            subscribers = list(self._subscribers.pop(channel, set()))

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for loop, queue in subscribers:
            if loop.is_closed():
                continue
            if current_loop is loop:
                queue.put_nowait(CHANNEL_CLOSE_SENTINEL)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, CHANNEL_CLOSE_SENTINEL)

    async def clear_all(self) -> None:
        """Clear all active subscriptions across all channels."""
        with self._lock:
            self._subscribers.clear()

    def subscriber_count(self, channel: str) -> int:
        """Get the current number of subscribers on a channel.

        Args:
            channel: Topic channel identifier.

        Returns:
            int: Number of active queues subscribed.
        """
        with self._lock:
            return len(self._subscribers.get(channel, set()))


# Global in-memory pubsub broker instance
in_memory_broker = InMemoryPubSub()

_redis_available_cached: bool | None = None
_redis_cache_timestamp: float = 0.0


async def is_redis_available(ttl_seconds: float = 5.0) -> bool:
    """Check whether Redis is currently accessible with short TTL caching.

    Args:
        ttl_seconds: Cache duration in seconds before re-checking Redis health.

    Returns:
        bool: True if Redis responds to health checks, False otherwise.
    """
    global _redis_available_cached, _redis_cache_timestamp
    now = time.monotonic()

    if _redis_available_cached is not None and (now - _redis_cache_timestamp < ttl_seconds):
        return _redis_available_cached

    try:
        _redis_available_cached = await check_redis_health()
    except Exception:
        _redis_available_cached = False

    _redis_cache_timestamp = now
    return _redis_available_cached


def reset_redis_availability_cache() -> None:
    """Reset cached Redis availability status (useful for tests)."""
    global _redis_available_cached, _redis_cache_timestamp
    _redis_available_cached = None
    _redis_cache_timestamp = 0.0


def get_channel_name(analysis_id: uuid.UUID | str) -> str:
    """Generate the canonical Redis/PubSub channel name for an analysis run.

    Args:
        analysis_id: Analysis identifier.

    Returns:
        str: Channel name in format 'analysis:{id}:steps'.
    """
    return f"analysis:{analysis_id}:steps"


def format_ws_message(
    analysis_id: uuid.UUID | str,
    message_type: str | WSMessageType,
    data: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Format a message payload conforming to LLD §7 and platform schema.

    Schema:
    {
        "type": "agent_step" | "status_change" | "error" | "complete",
        "analysis_id": str,
        "timestamp": str (ISO 8601 UTC),
        "data": { ... },
        ...optional top-level fields for LLD §7: agent, step_type, sequence_no, content, result
    }

    Args:
        analysis_id: Identifier of the analysis.
        message_type: Event type identifier.
        data: Nested payload dictionary.
        **extra: Additional fields (agent, step_type, sequence_no, content, result, error).

    Returns:
        dict[str, Any]: Standardized message dictionary.
    """
    timestamp = datetime.now(UTC).isoformat()
    type_str = str(message_type.value if isinstance(message_type, WSMessageType) else message_type)

    payload_data = dict(data) if data is not None else {}

    # If top-level fields are passed, ensure they exist both at top level and in data
    message: dict[str, Any] = {
        "type": type_str,
        "analysis_id": str(analysis_id),
        "timestamp": timestamp,
        "data": payload_data,
    }

    # Populate LLD §7 compatibility top-level fields if provided
    for key in ("agent", "step_type", "sequence_no", "content", "result", "error"):
        if key in extra and extra[key] is not None:
            message[key] = extra[key]
            if key not in message["data"]:
                message["data"][key] = extra[key]
        elif key in message["data"] and message["data"][key] is not None:
            message[key] = message["data"][key]

    return message


def format_agent_step_message(
    analysis_id: uuid.UUID | str,
    agent_name: str,
    step_type: str,
    content: dict[str, Any],
    sequence_no: int,
) -> dict[str, Any]:
    """Build a standardized agent step message conforming to LLD §7."""
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.AGENT_STEP,
        data={
            "agent": agent_name,
            "step_type": step_type,
            "sequence_no": sequence_no,
            "content": content,
        },
        agent=agent_name,
        step_type=step_type,
        sequence_no=sequence_no,
        content=content,
    )


def format_status_change_message(
    analysis_id: uuid.UUID | str,
    status: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a status change notification message."""
    data = {"status": status}
    if details:
        data.update(details)
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.STATUS_CHANGE,
        data=data,
    )


def format_error_message(
    analysis_id: uuid.UUID | str,
    error: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an error notification message."""
    data = {"error": error}
    if details:
        data.update(details)
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.ERROR,
        data=data,
        error=error,
    )


def format_complete_message(
    analysis_id: uuid.UUID | str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build an analysis complete notification message conforming to LLD §7."""
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.COMPLETE,
        data={"result": result},
        result=result,
    )


def format_analysis_done_message(
    analysis_id: uuid.UUID | str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build an analysis complete notification message conforming to LLD §7."""
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.ANALYSIS_DONE_UPPER,
        data={"result": result},
        result=result,
    )


def format_analysis_error_message(
    analysis_id: uuid.UUID | str,
    error: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an analysis error notification message conforming to LLD §7."""
    data = {"error": error}
    if details:
        data.update(details)
    return format_ws_message(
        analysis_id=analysis_id,
        message_type=WSMessageType.ANALYSIS_ERROR_UPPER,
        data=data,
        error=error,
    )


async def publish_step(
    analysis_id: uuid.UUID | str,
    step_dict: dict[str, Any],
) -> None:
    """Serialize and publish an execution step or event to the analysis channel.

    Publishes to Redis channel `analysis:{id}:steps`. If Redis is offline or
    unavailable, automatically falls back to the in-memory broker without failing.
    When analysis completes or fails, publishes the terminal message and closes
    the channel.

    Args:
        analysis_id: UUID or string identifier of the analysis.
        step_dict: Dictionary representing the event payload.
    """
    # Normalize message dictionary
    msg = dict(step_dict)
    if "analysis_id" not in msg:
        msg["analysis_id"] = str(analysis_id)
    else:
        msg["analysis_id"] = str(msg["analysis_id"])

    if "type" not in msg:
        msg["type"] = WSMessageType.AGENT_STEP.value

    if "timestamp" not in msg:
        msg["timestamp"] = datetime.now(UTC).isoformat()

    if "data" not in msg:
        msg["data"] = {
            k: v for k, v in msg.items() if k not in ("type", "analysis_id", "timestamp")
        }

    # Populate top-level fields for LLD §7 compatibility if found in data
    data_dict = msg.get("data", {})
    if isinstance(data_dict, dict):
        for field in ("agent", "step_type", "sequence_no", "content", "result", "error"):
            if field in data_dict and field not in msg:
                msg[field] = data_dict[field]

    # JSON serialization with fallback for datetimes/UUIDs
    json_str = json.dumps(msg, default=str)
    channel = get_channel_name(analysis_id)

    # 1. Attempt Redis publication if Redis is available
    redis_published = False
    if await is_redis_available():
        try:
            redis_client = await get_redis_client()
            await redis_client.publish(channel, json_str)
            await redis_client.aclose()
            redis_published = True
            logger.debug("Published step to Redis channel '%s'", channel)
        except Exception as exc:
            logger.debug(
                "Redis publish skipped or failed for '%s' (%s); delivering via in-memory",
                channel,
                exc,
            )

    # 2. Always deliver to in-memory broker if subscribers exist or Redis failed
    if not redis_published or in_memory_broker.subscriber_count(channel) > 0:
        await in_memory_broker.publish(channel, json_str)

    # 3. Check for terminal event (complete, error, analysis_done, analysis_error)
    type_val = str(msg.get("type", "")).lower()
    step_type_val = str(msg.get("step_type", "")).upper()
    status_val = str(msg.get("data", {}).get("status", "")).upper()

    is_terminal = (
        type_val in ("complete", "error", "analysis_done", "analysis_error")
        or (type_val != "agent_step" and step_type_val in ("DONE", "ERROR"))
        or status_val in ("DONE", "COMPLETED", "FAILED")
    )

    if is_terminal:
        logger.debug("Terminal message detected for channel '%s'; closing channel", channel)
        await in_memory_broker.close_channel(channel)


async def subscribe_steps(
    analysis_id: uuid.UUID | str,
    force_in_memory: bool = False,
) -> AsyncGenerator[str, None]:
    """Subscribe to the analysis steps channel and stream message strings.

    Subscribes to `analysis:{id}:steps` on Redis if accessible; otherwise falls
    back seamlessly to the in-memory pub/sub broker.

    Args:
        analysis_id: Target analysis UUID or string.
        force_in_memory: Force using in-memory pub/sub broker (useful for testing).

    Yields:
        str: Raw JSON message string received from the pub/sub channel.
    """
    channel = get_channel_name(analysis_id)
    use_redis = False
    redis_client = None
    pubsub = None

    if not force_in_memory and await is_redis_available():
        try:
            redis_client = await get_redis_client()
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel)
            use_redis = True
            logger.debug("Subscribed to Redis channel '%s'", channel)
        except Exception as exc:
            logger.warning("Redis subscription failed (%s); falling back to in-memory", exc)
            use_redis = False

    if use_redis and pubsub is not None:
        try:
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                except TimeoutError:
                    continue
                if message is None:
                    await asyncio.sleep(0.05)
                    continue
                if message.get("type") == "message":
                    raw_data = message.get("data")
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8")
                    yield str(raw_data)
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
            if redis_client is not None:
                with contextlib.suppress(Exception):
                    await redis_client.aclose()
    else:
        # Fallback to in-memory subscription
        queue = await in_memory_broker.subscribe(channel)
        try:
            while True:
                msg = await queue.get()
                if msg == CHANNEL_CLOSE_SENTINEL:
                    break
                yield msg
        finally:
            await in_memory_broker.unsubscribe(channel, queue)
