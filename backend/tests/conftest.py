"""Shared pytest fixtures for backend unit and integration test suites."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend directory is in sys.path so 'app' can always be imported
_BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import Base, get_db
from app.data_sources.mock_internal import MockInternalDataSource
from app.data_sources.registry import DataSourceRegistry
from app.llm.mock_provider import MockLLMProvider
from app.main import app


@pytest.fixture(autouse=True)
def default_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests run in mock LLM mode and MCP disabled by default unless explicitly overridden."""
    monkeypatch.setattr(settings, "MOCK_LLM", True)
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setattr(settings, "SINGSTAT_MCP_ENABLED", False)
    monkeypatch.setenv("SINGSTAT_MCP_ENABLED", "false")


@pytest_asyncio.fixture
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_db(async_db_session: AsyncSession) -> AsyncSession:
    """Convenience alias for async_db_session."""
    return async_db_session


@pytest.fixture
def mock_llm_provider() -> MockLLMProvider:
    """Provide a fresh MockLLMProvider instance for testing."""
    return MockLLMProvider()


@pytest.fixture
def mock_data_registry() -> DataSourceRegistry:
    """Provide an isolated DataSourceRegistry preloaded with MockInternalDataSource only."""
    registry = DataSourceRegistry()
    registry.register(MockInternalDataSource())
    return registry


@pytest_asyncio.fixture
async def test_client(
    async_db_session: AsyncSession,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an asynchronous httpx test client with in-memory database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
