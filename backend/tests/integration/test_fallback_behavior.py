"""Integration tests for LLMRouter failover and multi-agent fallback behavior.

Validates Story S30 acceptance criteria:
- Configure LLMRouter with mock primary that always fails
- Verify fallback provider called
- Verify analysis still completes with DONE status
- Configure both providers to fail -> analysis status is FAILED
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.graph import run_analysis
from app.core.config import settings
from app.core.database import Base
from app.crud.analysis import create_analysis, get_analysis
from app.data_sources import MockInternalDataSource, data_source_registry
from app.llm.base import AbstractLLMProvider, LLMResponse
from app.llm.exceptions import AllProvidersFailedError, LLMProviderError
from app.llm.mock_provider import MockLLMProvider
from app.llm.router import LLMRouter
from app.schemas.analysis import AnalysisStatus


class FailingLLMProvider(AbstractLLMProvider):
    """Provider that always fails on completion requests."""

    def __init__(self, name: str = "failing-primary") -> None:
        self.provider_name = name
        self.call_count = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, temperature, max_tokens, json_mode, kwargs
        self.call_count += 1
        raise LLMProviderError(
            f"{self.provider_name} service unavailable",
            provider=self.provider_name,
            is_retryable=False,
        )

    async def health_check(self) -> bool:
        return False


class TrackingMockLLMProvider(MockLLMProvider):
    """Mock provider that records completion invocation counts."""

    def __init__(self, name: str = "tracking-fallback") -> None:
        super().__init__(model=name)
        self.provider_name = name
        self.call_count = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        self.call_count += 1
        return await super().complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            **kwargs,
        )


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
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

    await engine.dispose()


@pytest.fixture(autouse=True)
def setup_mock_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure environment for mock LLM and mock data sources."""
    monkeypatch.setattr(settings, "MOCK_LLM", True)
    monkeypatch.setattr(settings, "USE_MOCK_DATA_SOURCES", True)
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_DATA_SOURCES", "true")

    mock_src = MockInternalDataSource()
    data_source_registry.register(mock_src, overwrite=True)


@pytest.mark.asyncio
async def test_primary_fails_and_fallback_succeeds_analysis_done(
    async_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When primary provider fails, router failovers to fallback, completing with DONE status."""
    failing_primary = FailingLLMProvider(name="failing-primary")
    working_fallback = TrackingMockLLMProvider(name="working-fallback")

    test_router = LLMRouter(
        primary=failing_primary,
        fallback=working_fallback,
        mock_mode=False,
        llm_fallback=True,
        max_retries=1,
        backoff_factor=0.0,
    )

    # Patch get_llm_router to return test_router across coordinator and analysis service
    monkeypatch.setattr("app.agents.coordinator.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.services.analysis_service.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.llm.router.get_llm_router", lambda: test_router)

    analysis_id = uuid.uuid4()
    query = "Analyze wage disparity and employment in Singapore ICT sector"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    # Run analysis pipeline
    final_state = await run_analysis(
        analysis_id=analysis_id,
        query=query,
        db=async_db,
    )

    assert final_state is not None

    # Assert primary was called and failed
    assert failing_primary.call_count >= 1, "Primary provider was not called"

    # Assert fallback was called and handled the completion
    assert working_fallback.call_count >= 1, "Fallback provider was not called"

    # Verify analysis still completes with DONE status
    analysis_record = await get_analysis(async_db, analysis_id)
    assert analysis_record is not None
    assert analysis_record.status == AnalysisStatus.DONE
    assert analysis_record.result is not None


@pytest.mark.asyncio
async def test_both_providers_fail_analysis_status_failed(
    async_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both primary and fallback providers fail, analysis status transitions to FAILED."""
    failing_primary = FailingLLMProvider(name="failing-primary")
    failing_fallback = FailingLLMProvider(name="failing-fallback")

    test_router = LLMRouter(
        primary=failing_primary,
        fallback=failing_fallback,
        mock_mode=False,
        llm_fallback=True,
        max_retries=1,
        backoff_factor=0.0,
    )

    # Verify router directly raises AllProvidersFailedError
    with pytest.raises(AllProvidersFailedError):
        await test_router.complete([{"role": "user", "content": "test"}])

    monkeypatch.setattr("app.agents.coordinator.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.services.analysis_service.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.llm.router.get_llm_router", lambda: test_router)

    analysis_id = uuid.uuid4()
    query = "Critical economic indicator query requiring LLM reasoning"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    # Run analysis pipeline - unhandled exception sets FAILED
    result_state = await run_analysis(
        analysis_id=analysis_id,
        query=query,
        db=async_db,
        raise_exceptions=False,
    )

    assert result_state.get("status") == "failed"

    # Verify analysis record in database is marked FAILED
    analysis_record = await get_analysis(async_db, analysis_id)
    assert analysis_record is not None
    assert analysis_record.status == AnalysisStatus.FAILED
    assert analysis_record.error_msg is not None
    err_text = f"{analysis_record.error_msg} {analysis_record.metadata_.get('technical_error', '') if analysis_record.metadata_ else ''}".lower()
    assert "providers failed" in err_text or "temporarily unavailable" in err_text


@pytest.mark.asyncio
async def test_primary_fails_and_fallback_disabled_analysis_status_failed(
    async_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When primary provider fails and llm_fallback=False (default), fallback is not invoked and analysis fails."""
    failing_primary = FailingLLMProvider(name="failing-primary")
    working_fallback = TrackingMockLLMProvider(name="working-fallback")

    test_router = LLMRouter(
        primary=failing_primary,
        fallback=working_fallback,
        mock_mode=False,
        llm_fallback=False,
        max_retries=1,
        backoff_factor=0.0,
    )

    monkeypatch.setattr("app.agents.coordinator.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.services.analysis_service.get_llm_router", lambda: test_router)
    monkeypatch.setattr("app.llm.router.get_llm_router", lambda: test_router)

    analysis_id = uuid.uuid4()
    query = "Analyze productivity metrics when fallback is disabled"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    result_state = await run_analysis(
        analysis_id=analysis_id,
        query=query,
        db=async_db,
        raise_exceptions=False,
    )

    assert result_state.get("status") == "failed"

    # Primary called, but fallback was NOT called
    assert failing_primary.call_count >= 1
    assert working_fallback.call_count == 0, (
        "Fallback provider should not be called when LLM_FALLBACK=False"
    )

    analysis_record = await get_analysis(async_db, analysis_id)
    assert analysis_record is not None
    assert analysis_record.status == AnalysisStatus.FAILED
    assert analysis_record.error_msg is not None
    err_text = f"{analysis_record.error_msg} {analysis_record.metadata_.get('technical_error', '') if analysis_record.metadata_ else ''}".lower()
    assert "fallback is disabled" in err_text or "temporarily unavailable" in err_text
