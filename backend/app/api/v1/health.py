"""Health check endpoint for platform service monitoring."""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.database import check_db_health
from app.core.redis import check_redis_health
from app.llm.router import LLMRouter, get_llm_router
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Module-level cache for LLM health status to avoid spamming external LLM APIs
_last_llm_health: dict[str, Any] | None = None
_last_llm_check_time: float = 0.0
_cached_router_id: int | None = None


def reset_health_cache() -> None:
    """Clear cached LLM health status (useful for unit tests and cache invalidation)."""
    global _last_llm_health, _last_llm_check_time, _cached_router_id
    _last_llm_health = None
    _last_llm_check_time = 0.0
    _cached_router_id = None


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Platform health status",
    description="Check connectivity to database, Redis, and configured LLM providers.",
)
async def health_check(
    check_llm: bool = Query(
        True,
        description="Whether to probe LLM providers. Live checks are cached for 60s to prevent spamming external APIs.",
    ),
    force_llm_check: bool = Query(
        False,
        description="Bypass the 60s cache and force an immediate live probe to LLM providers.",
    ),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> HealthResponse:
    """Perform health checks across PostgreSQL, Redis, and optionally LLM providers.

    Returns:
        HealthResponse: Status of DB, Redis, LLM providers, environment, and ISO 8601 timestamp.
    """
    global _last_llm_health, _last_llm_check_time, _cached_router_id

    db_ok = await check_db_health()
    redis_ok = await check_redis_health()

    llm_status: dict[str, Any] | None = None
    if check_llm:
        now = time.time()
        cache_ttl = getattr(settings, "LLM_HEALTH_CHECK_CACHE_TTL", 60.0)
        current_router_id = id(llm_router)

        if (
            not force_llm_check
            and _last_llm_health is not None
            and _cached_router_id == current_router_id
            and (now - _last_llm_check_time < cache_ttl)
        ):
            logger.debug(
                "Using cached LLM health status (age: %.1fs, ttl: %.1fs)",
                now - _last_llm_check_time,
                cache_ttl,
            )
            llm_status = _last_llm_health
        else:
            logger.info("Executing live LLM provider health check probe...")
            llm_status = await llm_router.check_health()
            _last_llm_health = llm_status
            _last_llm_check_time = now
            _cached_router_id = current_router_id

    status = "ok"
    if not db_ok:
        logger.warning("Health check detected database connectivity issue.")
    if not redis_ok:
        logger.warning("Health check detected Redis connectivity issue (non-fatal).")
    if (
        llm_status
        and llm_status.get("primary", {}).get("status") != "ok"
        and llm_status.get("fallback", {}).get("status") != "ok"
    ):
        logger.warning("Health check detected both primary and fallback LLMs down.")

    return HealthResponse(
        status=status,
        db="ok" if db_ok else "error",
        redis="ok" if redis_ok else "error",
        llm=llm_status,
        timestamp=datetime.now(UTC).isoformat(),
        environment=settings.ENVIRONMENT,
    )
