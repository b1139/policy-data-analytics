"""Async Redis connection pool and client dependency management."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """Get or create the global Redis connection pool.

    Returns:
        ConnectionPool: Shared Redis async connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=5.0,
            socket_timeout=30.0,
        )
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    """Create a Redis client using the shared connection pool.

    Returns:
        aioredis.Redis: Active Redis client instance.
    """
    pool = get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Provide an async Redis client dependency for FastAPI routes.

    Yields:
        aioredis.Redis: Redis client connected to the pool.
    """
    client = await get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def check_redis_health() -> bool:
    """Safely check if Redis is accessible with a PING command.

    Returns:
        bool: True if Redis responds to ping, False otherwise.
    """
    client: aioredis.Redis | None = None
    try:
        client = await get_redis_client()
        pong = await asyncio.wait_for(client.ping(), timeout=0.1)
        return bool(pong)
    except Exception as exc:
        logger.debug("Redis health check failed: %s", exc)
        return False
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


async def close_redis_pool() -> None:
    """Close the global Redis connection pool during application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.disconnect()
            logger.info("Redis connection pool disconnected.")
        except Exception as exc:
            logger.warning("Error disconnecting Redis pool: %s", exc)
        finally:
            _redis_pool = None
