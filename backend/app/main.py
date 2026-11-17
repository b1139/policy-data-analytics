"""FastAPI application factory, lifespan management, and route registry."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend directory is in sys.path when executed directly or imported
_BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.core.redis import close_redis_pool

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "Health",
        "description": "System health inspection and monitoring endpoints.",
    },
    {
        "name": "Analysis",
        "description": "Orchestration, status tracking, and export of multi-agent policy data analyses.",
    },
    {
        "name": "WebSocket",
        "description": "Real-time agent execution step and status streaming over WebSocket.",
    },
    {
        "name": "Root",
        "description": "Platform entry point and operational status metadata.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Manage application startup and shutdown lifecycle events."""
    setup_logging(level=settings.LOG_LEVEL)
    logger.info("Starting up %s (env: %s)...", settings.PROJECT_NAME, settings.ENVIRONMENT)

    # Initialize database tables
    await init_db()

    # Discover and initialize data source registry
    from app.data_sources import auto_register_sources, data_source_registry

    auto_register_sources()
    logger.info(
        "Data source registry initialized with sources: %s", data_source_registry.list_all()
    )

    yield

    # Clean up connections on shutdown
    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    await close_redis_pool()
    await close_db()
    logger.info("Application shutdown completed cleanly.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Agentic Policy Data Analytics Platform - Autonomous Multi-Agent API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    # Request ID middleware (first in chain to generate correlation ID)
    application.add_middleware(RequestIdMiddleware)

    # Configure CORS middleware
    origins = (
        settings.cors_origins
        if hasattr(settings, "cors_origins")
        else (
            settings.CORS_ORIGINS
            if isinstance(settings.CORS_ORIGINS, list)
            else [str(settings.CORS_ORIGINS)]
        )
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API v1 router
    application.include_router(api_v1_router, prefix=settings.API_V1_STR)

    # Direct /ws/analysis/{analysis_id} WebSocket stream endpoint
    from app.api.v1.websocket import router as websocket_router

    application.include_router(websocket_router, prefix="")

    @application.get("/", tags=["Root"], summary="Platform root status")
    async def root() -> dict[str, str]:
        """Root endpoint returning platform status and links."""
        return {
            "app": settings.PROJECT_NAME,
            "version": "0.1.0",
            "status": "operational",
            "docs": "/docs",
            "api_v1": settings.API_V1_STR,
        }

    return application


app = create_app()
