"""Unit tests for database module, engine, and get_db dependency."""

import inspect

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.database import AsyncSessionLocal, Base, engine, get_db


def test_database_engine_and_session_factory():
    """Verify engine and sessionmaker configuration."""
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
