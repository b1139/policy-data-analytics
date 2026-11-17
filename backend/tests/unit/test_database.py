"""Unit tests for database module, engine, session management, and health checks."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects.postgresql import JSONB

import app.core.database as db_module
from app.core.database import (
    AsyncSessionLocal,
    Base,
    _compile_jsonb_sqlite,
    check_db_health,
    close_db,
    engine,
    get_db,
    init_db,
)


def test_database_engine_and_session_factory():
    """Verify engine and sessionmaker configuration."""
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

    assert isinstance(engine, AsyncEngine)
    assert isinstance(AsyncSessionLocal, async_sessionmaker)


def test_base_metadata_contains_all_models():
    """Verify that Base.metadata has registered all required tables."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {"analyses", "agent_logs", "datasets", "analysis_datasets"}
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_get_db_is_async_generator():
    """Verify that get_db is an async generator function."""
    assert inspect.isasyncgenfunction(get_db)


def test_compile_jsonb_sqlite():
    """Verify JSONB compiles as JSON on SQLite dialect."""
    compiler = MagicMock()
    type_ = JSONB()
    result = _compile_jsonb_sqlite(type_, compiler)
    assert result == "JSON"


@pytest.mark.asyncio
async def test_get_db_session_commit_and_close():
    """Verify get_db commits on success and closes session."""
    mock_session = AsyncMock()
    mock_session_local = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch.object(db_module, "AsyncSessionLocal", mock_session_local):
        gen = get_db()
        session = await gen.asend(None)
        assert session == mock_session
        with pytest.raises(StopAsyncIteration):
            await gen.asend(None)

    mock_session.commit.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_session_rollback_on_error():
    """Verify get_db rolls back on unhandled exceptions and closes."""
    mock_session = AsyncMock()
    mock_session_local = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch.object(db_module, "AsyncSessionLocal", mock_session_local):
        gen = get_db()
        session = await gen.asend(None)
        assert session == mock_session
        with pytest.raises(ValueError, match="Boom"):
            await gen.athrow(ValueError("Boom"))

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_db_success():
    """Verify init_db initializes tables cleanly using run_sync."""
    mock_conn = AsyncMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__.return_value = mock_conn
    mock_begin.__aexit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_begin

    with patch.object(db_module, "engine", mock_engine):
        await init_db()
        mock_conn.run_sync.assert_awaited_once_with(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_init_db_fallback_to_sqlite():
    """Verify init_db falls back to local sqlite when postgresql connection fails."""
    mock_engine = MagicMock()
    mock_engine.begin.side_effect = RuntimeError("Postgres unreachable")

    original_engine = db_module.engine
    original_session = db_module.AsyncSessionLocal

    with (
        patch.object(db_module, "engine", mock_engine),
        patch(
            "app.core.database.settings.DATABASE_URL",
            "postgresql+asyncpg://user:pass@localhost:5432/db",
        ),
    ):
        await init_db()

    # Restore original references
    db_module.engine = original_engine
    db_module.AsyncSessionLocal = original_session
    db_module.async_session_factory = original_session


@pytest.mark.asyncio
async def test_close_db_success_and_exception():
    """Verify close_db disposes engine and catches exceptions gracefully."""
    mock_engine = AsyncMock()
    with patch.object(db_module, "engine", mock_engine):
        await close_db()
        mock_engine.dispose.assert_awaited_once()

    # Test error suppression
    mock_error_engine = AsyncMock()
    mock_error_engine.dispose.side_effect = RuntimeError("Dispose failure")
    with patch.object(db_module, "engine", mock_error_engine):
        # Should not raise
        await close_db()


@pytest.mark.asyncio
async def test_check_db_health():
    """Verify check_db_health returns True on healthy DB and False on error."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_local = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch.object(db_module, "AsyncSessionLocal", mock_session_local):
        assert await check_db_health() is True

    # Test failure
    mock_fail_session = MagicMock()
    mock_fail_session.__aenter__.side_effect = RuntimeError("Connection timed out")
    with patch.object(db_module, "AsyncSessionLocal", mock_fail_session):
        assert await check_db_health() is False
