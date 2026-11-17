"""Integration test for verifying agent execution sequence and state transitions.

Validates Story S30 acceptance criteria:
- Verify coordinator runs first (lowest sequence_no agent_logs)
- Verify extraction runs second
- Verify analytics runs last
- Verify research_plan populated after coordinator step
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

from app.agents.analytics import analytics_node
from app.agents.coordinator import coordinator_node
from app.agents.extraction import extraction_node
from app.agents.graph import run_analysis
from app.agents.state import AgentName, create_initial_state
from app.core.config import settings
from app.core.database import Base
from app.crud.analysis import create_analysis
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
async def test_coordinator_populates_research_plan(async_db: AsyncSession) -> None:
    """Verify research_plan is populated after the coordinator agent step."""
    analysis_id = uuid.uuid4()
    query = "Analyze wage growth and tech employment trends in Singapore"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    state = create_initial_state(analysis_id=str(analysis_id), query=query)
    assert state.get("research_plan") is None

    # Execute coordinator node
    updated_state = await coordinator_node(state, db=async_db)

    # Verify research_plan populated after coordinator step
    plan = updated_state.get("research_plan")
    assert plan is not None
    assert isinstance(plan, dict)
    assert "sources" in plan and len(plan["sources"]) > 0
    assert "topics" in plan and len(plan["topics"]) > 0
    assert "sub_tasks" in plan and len(plan["sub_tasks"]) > 0
    assert updated_state.get("current_agent") == AgentName.COORDINATOR


@pytest.mark.asyncio
async def test_agent_execution_sequence_in_database(async_db: AsyncSession) -> None:
    """Verify sequence_no order of agent logs: coordinator -> extraction -> analytics."""
    analysis_id = uuid.uuid4()
    query = "What is the unemployment rate in Singapore over the past 5 years?"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    # Execute full multi-agent pipeline
    await run_analysis(
        analysis_id=analysis_id,
        query=query,
        db=async_db,
    )

    # Fetch all agent logs ordered by sequence_no
    stmt = (
        select(AgentLog)
        .where(AgentLog.analysis_id == analysis_id)
        .order_by(AgentLog.sequence_no.asc())
    )
    res = await async_db.execute(stmt)
    logs = list(res.scalars().all())

    assert len(logs) >= 3, f"Expected at least 3 logs, got {len(logs)}"

    # Partition logs by agent
    coord_logs = [item for item in logs if item.agent_name in (AgentName.COORDINATOR, "coordinator")]
    extract_logs = [item for item in logs if item.agent_name in (AgentName.EXTRACTION, "extraction")]
    analytics_logs = [item for item in logs if item.agent_name in (AgentName.ANALYTICS, "analytics")]

    assert len(coord_logs) > 0, "Coordinator agent logs missing"
    assert len(extract_logs) > 0, "Extraction agent logs missing"
    assert len(analytics_logs) > 0, "Analytics agent logs missing"

    # Verify coordinator runs first (lowest sequence_no agent_logs)
    min_coord_seq = min(item.sequence_no for item in coord_logs)
    max_coord_seq = max(item.sequence_no for item in coord_logs)
    assert min_coord_seq == 1, f"Coordinator must start at sequence_no 1, got {min_coord_seq}"

    # Verify extraction runs second
    min_extract_seq = min(item.sequence_no for item in extract_logs)
    max_extract_seq = max(item.sequence_no for item in extract_logs)
    assert max_coord_seq < min_extract_seq, (
        f"Coordinator max sequence {max_coord_seq} must be < extraction min sequence {min_extract_seq}"
    )

    # Verify analytics runs last
    min_analytics_seq = min(item.sequence_no for item in analytics_logs)
    max_analytics_seq = max(item.sequence_no for item in analytics_logs)
    assert max_extract_seq < min_analytics_seq, (
        f"Extraction max sequence {max_extract_seq} must be < analytics min sequence {min_analytics_seq}"
    )
    assert max_analytics_seq >= min_analytics_seq

    # Verify global ordering of agents in logs list
    first_agent = logs[0].agent_name
    assert first_agent in (AgentName.COORDINATOR, "coordinator")

    last_agent = logs[-1].agent_name
    assert last_agent in (AgentName.ANALYTICS, "analytics")


@pytest.mark.asyncio
async def test_step_by_step_node_chain(async_db: AsyncSession) -> None:
    """Verify sequential node execution passes accumulated state correctly."""
    analysis_id = uuid.uuid4()
    query = "Singapore GDP and labor productivity"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    state = create_initial_state(analysis_id=str(analysis_id), query=query)

    # 1. Step 1: Coordinator
    state = await coordinator_node(state, db=async_db)
    assert state["current_agent"] == AgentName.COORDINATOR
    assert state.get("research_plan") is not None
    assert len(state.get("research_plan", {}).get("sources", [])) > 0

    # 2. Step 2: Extraction
    state = await extraction_node(state, db=async_db)
    assert state["current_agent"] == AgentName.EXTRACTION
    assert len(state.get("selected_datasets", [])) > 0

    # 3. Step 3: Analytics
    state = await analytics_node(state, db=async_db)
    assert state["current_agent"] == AgentName.ANALYTICS
    assert state.get("insights") is not None
    assert len(state.get("charts", [])) > 0
