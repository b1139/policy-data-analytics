"""SQLAlchemy 2.0 async database configuration and session management."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


# Provide SQLite dialect compatibility for JSONB during tests
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:  # noqa: ARG001
    """Render JSONB as JSON in SQLite for unit testing environments."""
    return "JSON"


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


# Async engine configuration
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.LOG_LEVEL.upper() == "DEBUG",
    future=True,
    pool_pre_ping=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
async_session_factory = AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session dependency for FastAPI routes.

    Yields:
        AsyncSession: Active database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables during application startup."""
    global engine, AsyncSessionLocal, async_session_factory
    try:
        import app.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created successfully.")
    except Exception as exc:
        logger.warning("Primary database connection could not complete: %s", exc)
        # Attempt graceful fallback to local SQLite database if PostgreSQL is unreachable
        if "postgresql" in settings.DATABASE_URL.lower():
            try:
                import aiosqlite  # noqa: F401
                fallback_url = "sqlite+aiosqlite:///./policy_analytics.db"
                logger.info("Switching to local SQLite fallback database: %s", fallback_url)
                fallback_engine = create_async_engine(fallback_url, future=True)
                async with fallback_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                engine = fallback_engine
                AsyncSessionLocal = async_sessionmaker(
                    bind=engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autocommit=False,
                    autoflush=False,
                )
                async_session_factory = AsyncSessionLocal
                logger.info("Local SQLite fallback database tables initialized successfully.")
            except Exception as fb_exc:
                logger.warning("Local SQLite fallback could not be initialized: %s", fb_exc)


async def close_db() -> None:
    """Dispose database engine connections during shutdown."""
    try:
        await engine.dispose()
        logger.info("Database engine connections closed.")
    except Exception as exc:
        logger.warning("Error closing database engine connections: %s", exc)


async def check_db_health() -> bool:
    """Safely check database connectivity by running a lightweight query.

    Returns:
        bool: True if DB responds to 'SELECT 1', False otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False
