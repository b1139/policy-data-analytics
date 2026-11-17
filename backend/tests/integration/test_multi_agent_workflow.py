"""Integration tests for end-to-end multi-agent workflow orchestration and ReAct execution.

Validates Story S15 acceptance criteria:
- build_graph() wires coordinator -> extraction -> conditional edge -> analytics -> END
- Execution runs full graph with USE_MOCK_DATA_SOURCES=true and MOCK_LLM=true
- Analysis database record transitions from PENDING -> RUNNING -> DONE with result payload
- WebSocket receives >= 5 step messages + 1 ANALYSIS_DONE event
- AnalysisResult payload contains {insights, charts, citations, stats_summary, generated_at, truncated_preview}
- Conditional edge after extraction routes to END with FAILED when 0 datasets and extraction errors exist
- Unhandled exception updates Analysis record to FAILED and emits ANALYSIS_ERROR event
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.graph import build_graph, run_analysis
from app.agents.state import AgentState
from app.core.config import settings
from app.core.database import Base, get_db
from app.crud.analysis import create_analysis, get_analysis
from app.data_sources import MockInternalDataSource, data_source_registry
from app.main import app
from app.models.agent_log import AgentLog
from app.schemas.analysis import AnalysisStatus
from app.services.pubsub import (
    CHANNEL_CLOSE_SENTINEL,
    get_channel_name,
    in_memory_broker,
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

    # Ensure mock internal data source is registered
    mock_src = MockInternalDataSource()
    data_source_registry.register(mock_src, overwrite=True)


@pytest.mark.asyncio
async def test_full_multi_agent_workflow_e2e(async_db: AsyncSession) -> None:
    """End-to-end integration test verifying complete multi-agent analysis execution.

    Verifies:
    1. Analysis record starts at PENDING, transitions through RUNNING, and finishes at DONE.
    2. Coordinator, extraction, and analytics nodes execute in sequence.
    3. Final AnalysisResult payload is persisted in the database with expected keys.
    4. WebSocket receives >= 5 step messages and 1 terminal ANALYSIS_DONE event.
    5. AgentLog records are persisted for each executed reasoning step.
    """
    analysis_id = uuid.uuid4()
    query = "What is the 5-year employment trend in Singapore's technology and ICT sector?"

    # Create initial Analysis record in database in PENDING status
    analysis_record = await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )
    assert analysis_record.status == AnalysisStatus.PENDING.value

    # Subscribe to analysis WebSocket pub/sub channel
    channel = get_channel_name(analysis_id)
    ws_queue = await in_memory_broker.subscribe(channel)

    try:
        # Execute run_analysis within the test async database session
        final_state = await run_analysis(
            analysis_id=analysis_id,
            query=query,
            db=async_db,
        )

        # 1. State assertions
        assert final_state["status"] == "completed"
        assert final_state["analysis_id"] == str(analysis_id)
        assert final_state.get("research_plan") is not None
        assert (
            len(final_state.get("selected_datasets", [])) > 0
            or len(final_state.get("raw_data", {})) > 0
        )
        assert final_state.get("statistical_results") is not None
        assert len(final_state.get("charts", [])) >= 1
        assert len(final_state.get("insights", [])) >= 1

        # 2. Database record verification
        updated_analysis = await get_analysis(async_db, analysis_id, include_logs=True)
        assert updated_analysis is not None
        assert updated_analysis.status == AnalysisStatus.DONE.value
        assert updated_analysis.error_msg is None
        assert updated_analysis.result is not None

        result_payload = updated_analysis.result
        assert "insights" in result_payload
        assert isinstance(result_payload["insights"], str)
        assert len(result_payload["insights"]) > 0
        assert "charts" in result_payload
        assert isinstance(result_payload["charts"], list)
        assert len(result_payload["charts"]) >= 1
        assert "citations" in result_payload
        assert isinstance(result_payload["citations"], list)
        assert "stats_summary" in result_payload
        assert isinstance(result_payload["stats_summary"], dict)
        assert "generated_at" in result_payload
        assert "truncated_preview" in result_payload

        # 3. AgentLog database verification
        logs_stmt = (
            select(AgentLog)
            .where(AgentLog.analysis_id == analysis_id)
            .order_by(AgentLog.sequence_no)
        )
        logs_result = await async_db.execute(logs_stmt)
        persisted_logs = list(logs_result.scalars().all())
        assert len(persisted_logs) >= 5, (
            f"Expected at least 5 persisted agent logs, found {len(persisted_logs)}"
        )

        # 4. WebSocket messages verification
        received_messages: list[dict[str, Any]] = []
        while not ws_queue.empty():
            raw_msg = ws_queue.get_nowait()
            if raw_msg == CHANNEL_CLOSE_SENTINEL:
                continue
            received_messages.append(json.loads(raw_msg))

        step_messages = [
            m for m in received_messages if m.get("type") in ("agent_step", "AGENT_STEP")
        ]
        done_messages = [
            m for m in received_messages if m.get("type") in ("ANALYSIS_DONE", "complete")
        ]
        status_change_messages = [m for m in received_messages if m.get("type") == "status_change"]

        assert len(status_change_messages) >= 1
        assert any(m.get("data", {}).get("status") == "RUNNING" for m in status_change_messages)
        assert len(step_messages) >= 5, f"Expected >= 5 step messages, got {len(step_messages)}"
        assert len(done_messages) >= 1, (
            f"Expected >= 1 ANALYSIS_DONE terminal event, got {len(done_messages)}"
        )

        # Validate terminal event structure
        terminal_msg = done_messages[-1]
        assert terminal_msg.get("type") in ("ANALYSIS_DONE", "complete")
        assert terminal_msg.get("result") is not None
        assert terminal_msg["result"]["insights"] == result_payload["insights"]

    finally:
        await in_memory_broker.unsubscribe(channel, ws_queue)


@pytest.mark.asyncio
async def test_conditional_edge_extraction_failure_routes_to_end(
    async_db: AsyncSession,
) -> None:
    """Verify conditional edge routes to END with FAILED when extraction fails with 0 datasets."""
    analysis_id = uuid.uuid4()
    query = "Analyze unavailable data source"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    channel = get_channel_name(analysis_id)
    ws_queue = await in_memory_broker.subscribe(channel)

    async def mock_failing_extraction(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        return {
            "current_agent": "extraction",
            "raw_datasets": [],
            "selected_datasets": [],
            "extraction_errors": [
                "Connection failed to remote source",
                "Dataset format unrecognized",
            ],
            "status": "extraction_failed",
        }

    visited_nodes: list[str] = []

    async def mock_coordinator(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("coordinator")
        return {
            "current_agent": "coordinator",
            "research_plan": {
                "query_intent": "Test failure",
                "planned_datasets": [{"source": "invalid", "dataset_id": "none"}],
            },
            "status": "planned",
        }

    async def mock_analytics(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("analytics")
        return {"current_agent": "analytics", "status": "completed"}

    graph = build_graph(
        coordinator_node_fn=mock_coordinator,
        extraction_node_fn=mock_failing_extraction,
        analytics_node_fn=mock_analytics,
    )

    try:
        final_state = await run_analysis(
            analysis_id=analysis_id,
            query=query,
            db=async_db,
            graph=graph,
        )

        # Analytics node must NOT have been visited
        assert "coordinator" in visited_nodes
        assert "analytics" not in visited_nodes

        # Workflow status should indicate failure
        assert final_state["status"] in ("failed", "extraction_failed")

        # Database record should be FAILED with error message
        db_record = await get_analysis(async_db, analysis_id)
        assert db_record is not None
        assert db_record.status == AnalysisStatus.FAILED.value
        assert db_record.error_msg is not None
        assert "Connection failed" in db_record.error_msg

        # WebSocket should receive ANALYSIS_ERROR terminal event
        received_messages: list[dict[str, Any]] = []
        while not ws_queue.empty():
            raw_msg = ws_queue.get_nowait()
            if raw_msg == CHANNEL_CLOSE_SENTINEL:
                continue
            received_messages.append(json.loads(raw_msg))

        error_messages = [
            m for m in received_messages if m.get("type") in ("ANALYSIS_ERROR", "error")
        ]
        assert len(error_messages) >= 1

    finally:
        await in_memory_broker.unsubscribe(channel, ws_queue)


@pytest.mark.asyncio
async def test_unhandled_exception_marks_analysis_failed(
    async_db: AsyncSession,
) -> None:
    """Verify unhandled exception during graph execution updates DB to FAILED and emits ANALYSIS_ERROR."""
    analysis_id = uuid.uuid4()
    query = "Query triggering unexpected crash"

    await create_analysis(
        db=async_db,
        query=query,
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
    )

    channel = get_channel_name(analysis_id)
    ws_queue = await in_memory_broker.subscribe(channel)

    async def exploding_coordinator(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        raise RuntimeError("Unexpected internal crash in coordinator node")

    graph = build_graph(
        coordinator_node_fn=exploding_coordinator,
    )

    try:
        result = await run_analysis(
            analysis_id=analysis_id,
            query=query,
            db=async_db,
            graph=graph,
            raise_exceptions=False,
        )

        assert result["status"] == "failed"
        assert "Unexpected internal crash" in result["error"]

        # Database record must be FAILED with error_msg
        db_record = await get_analysis(async_db, analysis_id)
        assert db_record is not None
        assert db_record.status == AnalysisStatus.FAILED.value
        assert "Unexpected internal crash" in (db_record.error_msg or "")

        # WebSocket received error event
        received_messages: list[dict[str, Any]] = []
        while not ws_queue.empty():
            raw_msg = ws_queue.get_nowait()
            if raw_msg == CHANNEL_CLOSE_SENTINEL:
                continue
            received_messages.append(json.loads(raw_msg))

        error_messages = [
            m for m in received_messages if m.get("type") in ("ANALYSIS_ERROR", "error")
        ]
        assert len(error_messages) >= 1
        assert "Unexpected internal crash" in error_messages[0].get("error", "")

    finally:
        await in_memory_broker.unsubscribe(channel, ws_queue)


@pytest.mark.asyncio
async def test_api_start_analysis_background_e2e(async_db: AsyncSession) -> None:
    """Verify POST /api/v1/analysis/start initiates analysis and runs pipeline to DONE."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "query": "Singapore ICT tech employment growth from 2019 to 2024",
                "metadata": {"source": "mock_internal"},
            }
            response = await client.post("/api/v1/analysis/start", json=payload)
            assert response.status_code == 201
            data = response.json()
            analysis_id = uuid.UUID(data["analysis_id"])
            assert data["status"] == "PENDING"
            assert "ws_url" in data

            # Execute analysis in database to simulate background worker
            await run_analysis(analysis_id=analysis_id, db=async_db)

            # Verify analysis record transitioned to DONE with result
            db_record = await get_analysis(async_db, analysis_id)
            assert db_record is not None
            assert db_record.status == AnalysisStatus.DONE.value
            assert db_record.result is not None
            assert "insights" in db_record.result
            assert "charts" in db_record.result
            assert len(db_record.result["charts"]) >= 1

    finally:
        app.dependency_overrides.clear()
