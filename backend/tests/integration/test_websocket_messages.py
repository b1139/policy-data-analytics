"""Integration tests for WebSocket streaming during multi-agent analysis.

Validates Story S30 acceptance criteria:
- Connect to WS endpoint or test client, run analysis, collect messages
- Assert: at least 1 AGENT_STEP message per agent
- Assert: final message is ANALYSIS_DONE
- Assert: messages arrive in sequence_no order
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.agents.graph import run_analysis
from app.agents.state import AgentName
from app.core.config import settings
from app.core.database import Base, get_db
from app.crud.analysis import create_analysis
from app.data_sources import MockInternalDataSource, data_source_registry
from app.main import app
from app.schemas.analysis import AnalysisStatus
from app.schemas.websocket import WSMessageType
from app.services.pubsub import (
    CHANNEL_CLOSE_SENTINEL,
    get_channel_name,
    in_memory_broker,
    reset_redis_availability_cache,
)


@pytest.fixture(autouse=True)
def setup_mock_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure environment for mock LLM, mock data sources, and in-memory broker."""
    reset_redis_availability_cache()
    monkeypatch.setattr(settings, "MOCK_LLM", True)
    monkeypatch.setattr(settings, "USE_MOCK_DATA_SOURCES", True)
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_DATA_SOURCES", "true")

    mock_src = MockInternalDataSource()
    data_source_registry.register(mock_src, overwrite=True)


@pytest.fixture(autouse=True)
def reset_broker_state() -> None:
    """Clear active in-memory broker subscribers before each test."""
    asyncio.run(in_memory_broker.clear_all())


@pytest.mark.asyncio
async def test_asyncio_pubsub_event_collection() -> None:
    """Collect messages from pubsub channel during run_analysis and verify criteria.

    Asserts:
    - At least 1 AGENT_STEP message per agent (coordinator, extraction, analytics)
    - Final message is ANALYSIS_DONE
    - Messages arrive in sequence_no order
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    analysis_id = uuid.uuid4()
    query = "Analyze wage disparity and employment in Singapore tech sector"

    async with session_factory() as session:
        await create_analysis(
            db=session,
            query=query,
            analysis_id=analysis_id,
            status=AnalysisStatus.PENDING,
        )

    # Subscribe to steps channel
    channel = get_channel_name(analysis_id)
    ws_queue = await in_memory_broker.subscribe(channel)

    try:
        # Run full analysis
        async with session_factory() as session:
            final_state = await run_analysis(
                analysis_id=analysis_id,
                query=query,
                db=session,
            )

        assert final_state["status"] == "completed"

        # Collect published messages
        collected: list[dict[str, Any]] = []
        while not ws_queue.empty():
            raw_msg = ws_queue.get_nowait()
            if raw_msg == CHANNEL_CLOSE_SENTINEL:
                continue
            collected.append(json.loads(raw_msg))

        assert len(collected) >= 4, f"Expected >= 4 messages, received {len(collected)}"

        # 1. Assert: at least 1 AGENT_STEP message per agent
        agent_step_messages = [
            m
            for m in collected
            if m.get("type")
            in (WSMessageType.AGENT_STEP.value, WSMessageType.AGENT_STEP_UPPER.value)
        ]
        assert len(agent_step_messages) >= 3

        agents_seen = {m.get("agent") for m in agent_step_messages}
        assert "coordinator" in agents_seen or AgentName.COORDINATOR in agents_seen, (
            f"Coordinator missing in agent steps: {agents_seen}"
        )
        assert "extraction" in agents_seen or AgentName.EXTRACTION in agents_seen, (
            f"Extraction missing in agent steps: {agents_seen}"
        )
        assert "analytics" in agents_seen or AgentName.ANALYTICS in agents_seen, (
            f"Analytics missing in agent steps: {agents_seen}"
        )

        # 2. Assert: final message is ANALYSIS_DONE
        terminal_msg = collected[-1]
        assert terminal_msg.get("type") in (
            WSMessageType.ANALYSIS_DONE_UPPER.value,
            WSMessageType.COMPLETE.value,
            "ANALYSIS_DONE",
        )
        assert terminal_msg.get("result") is not None

        # 3. Assert: messages arrive in sequence_no order
        seq_nos = [
            m["sequence_no"] for m in agent_step_messages if m.get("sequence_no") is not None
        ]
        assert len(seq_nos) >= 3
        assert seq_nos == sorted(seq_nos), f"Sequence numbers {seq_nos} not strictly non-decreasing"
        assert seq_nos == list(range(1, len(seq_nos) + 1)), (
            f"Sequence numbers {seq_nos} not sequential"
        )

    finally:
        await in_memory_broker.unsubscribe(channel, ws_queue)
        await engine.dispose()


def test_websocket_client_stream_live_pipeline() -> None:
    """Connect live TestClient WebSocket to /ws/analysis/{id}, run analysis, collect frames.

    Asserts:
    - Connect to WS endpoint via test client
    - At least 1 AGENT_STEP message per agent
    - Final message is ANALYSIS_DONE
    - Messages arrive in sequence_no order
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    analysis_id = uuid.uuid4()
    query = "Analyze wage disparity and employment in Singapore tech sector"

    async def prep_analysis() -> None:
        async with session_factory() as session:
            await create_analysis(
                db=session,
                query=query,
                analysis_id=analysis_id,
                status=AnalysisStatus.PENDING,
            )

    asyncio.run(prep_analysis())

    client = TestClient(app)
    received_frames: list[dict[str, Any]] = []

    try:
        with client.websocket_connect(f"/ws/analysis/{analysis_id}") as ws:
            # 1. Initial connection message
            init_frame = ws.receive_json()
            assert init_frame.get("type") == "status_change"

            # Wait for subscriber to attach to the in-memory channel
            channel = get_channel_name(analysis_id)
            for _ in range(50):
                if in_memory_broker.subscriber_count(channel) >= 1:
                    break
                time.sleep(0.02)

            # Run analysis in background thread
            def run_worker() -> None:
                async def execute() -> None:
                    async with session_factory() as worker_session:
                        await run_analysis(
                            analysis_id=analysis_id,
                            query=query,
                            db=worker_session,
                        )

                asyncio.run(execute())

            worker_thread = threading.Thread(target=run_worker)
            worker_thread.start()

            # Collect incoming WebSocket frames until ANALYSIS_DONE
            while True:
                try:
                    frame = ws.receive_json()
                    received_frames.append(frame)
                    f_type = str(frame.get("type", "")).upper()
                    if f_type in ("ANALYSIS_DONE", "COMPLETE", "ERROR", "ANALYSIS_ERROR"):
                        break
                except Exception:
                    break

            worker_thread.join(timeout=10)

        assert len(received_frames) >= 4, f"Expected >= 4 frames, received {len(received_frames)}"

        # 1. Assert: at least 1 AGENT_STEP message per agent
        agent_steps = [f for f in received_frames if f.get("type") in ("AGENT_STEP", "agent_step")]
        assert len(agent_steps) >= 3

        agents_seen = {f.get("agent") for f in agent_steps}
        assert "coordinator" in agents_seen, f"Coordinator missing from {agents_seen}"
        assert "extraction" in agents_seen, f"Extraction missing from {agents_seen}"
        assert "analytics" in agents_seen, f"Analytics missing from {agents_seen}"

        # 2. Assert: final message is ANALYSIS_DONE
        final_frame = received_frames[-1]
        assert final_frame.get("type") in ("ANALYSIS_DONE", "complete"), (
            f"Expected ANALYSIS_DONE, got {final_frame.get('type')}"
        )
        assert final_frame.get("result") is not None

        # 3. Assert: messages arrive in sequence_no order
        seq_nos = [f["sequence_no"] for f in agent_steps if f.get("sequence_no") is not None]
        assert len(seq_nos) >= 3
        assert seq_nos == sorted(seq_nos), f"Sequence numbers {seq_nos} not ordered"
        assert seq_nos == list(range(1, len(seq_nos) + 1)), (
            f"Sequence numbers {seq_nos} not contiguous"
        )

    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
