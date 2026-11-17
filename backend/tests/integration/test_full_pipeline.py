"""Integration test for full multi-agent pipeline execution.

Validates Story S30 acceptance criteria:
- Full graph run: run_analysis(analysis_id, query) with mock providers
- Assert: Analysis.status == "DONE" after completion
- Assert: AgentLog rows exist for all 3 agents (coordinator, extraction, analytics)
- Assert: Analysis.result contains non-empty insights and charts
- Assert: at least 1 Dataset row created and linked to analysis
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.graph import run_analysis
from app.agents.state import AgentName
from app.core.config import settings
from app.core.database import Base
from app.crud.analysis import create_analysis, get_analysis
from app.crud.dataset import get_datasets_for_analysis
from app.data_sources import MockInternalDataSource, data_source_registry
from app.models.agent_log import AgentLog
from app.schemas.analysis import AnalysisStatus


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
async def test_full_pipeline_execution(async_db: AsyncSession) -> None:
    """Run full graph analysis with mock providers and verify all acceptance criteria."""
    analysis_id = uuid.uuid4()
    query = "What is the 5-year employment and wage growth trend in Singapore tech sector?"

    # 1. Create initial analysis record in DB
    analysis_record = await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )
    assert analysis_record.status == AnalysisStatus.PENDING

    # 2. Run analysis full graph
    final_state = await run_analysis(
        analysis_id=analysis_id,
        query=query,
        db=async_db,
    )

    assert final_state is not None

    # 3. Assert: Analysis.status == "DONE"
    updated_analysis = await get_analysis(async_db, analysis_id)
    assert updated_analysis is not None
    assert updated_analysis.status == AnalysisStatus.DONE

    # 4. Assert: Analysis.result contains non-empty insights and charts
    result = updated_analysis.result
    assert isinstance(result, dict)
    assert "insights" in result
    assert result["insights"] and len(result["insights"]) > 0
    assert "charts" in result
    assert isinstance(result["charts"], list)
    assert len(result["charts"]) > 0

    # 5. Assert: AgentLog rows exist for all 3 agents (coordinator, extraction, analytics)
    stmt = (
        select(AgentLog)
        .where(AgentLog.analysis_id == analysis_id)
        .order_by(AgentLog.sequence_no.asc())
    )
    res = await async_db.execute(stmt)
    logs = list(res.scalars().all())
    assert len(logs) > 0

    agent_names = {log.agent_name for log in logs}
    assert AgentName.COORDINATOR in agent_names or "coordinator" in agent_names
    assert AgentName.EXTRACTION in agent_names or "extraction" in agent_names
    assert AgentName.ANALYTICS in agent_names or "analytics" in agent_names

    # 6. Assert: at least 1 Dataset row created and linked to analysis
    associated_datasets = await get_datasets_for_analysis(async_db, analysis_id)
    assert len(associated_datasets) >= 1
    for ds in associated_datasets:
        assert ds.id is not None
        assert ds.source is not None
