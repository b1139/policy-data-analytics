"""WebSocket concurrency and load test suite for real-time analysis streaming.

Validates Story S32 acceptance criteria:
- 10 concurrent WebSocket connections to same analysis
- All connections receive all messages
- No messages dropped
"""

from __future__ import annotations

import asyncio
import contextlib
import os
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
from sqlalchemy.pool import NullPool

from app.agents.graph import run_analysis
from app.core.config import settings
from app.core.database import Base, get_db
from app.crud.analysis import create_analysis
from app.data_sources import MockInternalDataSource, data_source_registry
from app.main import app
from app.schemas.analysis import AnalysisStatus
from app.services.pubsub import (
    format_agent_step_message,
    format_analysis_done_message,
    get_channel_name,
    in_memory_broker,
    publish_step,
    reset_redis_availability_cache,
)


@pytest.fixture(autouse=True)
def configure_mock_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure mock LLM, mock data sources, and in-memory broker are strictly active."""
    reset_redis_availability_cache()
    monkeypatch.setattr(settings, "MOCK_LLM", True)
    monkeypatch.setattr(settings, "USE_MOCK_DATA_SOURCES", True)
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("USE_MOCK_DATA_SOURCES", "true")

    mock_ds = MockInternalDataSource()
    data_source_registry.register(mock_ds, overwrite=True)


@pytest.fixture(autouse=True)
def reset_in_memory_broker() -> None:
    """Clear in-memory pubsub broker subscribers before each test."""
    asyncio.run(in_memory_broker.clear_all())


def test_10_concurrent_websockets_receive_all_messages() -> None:
    """Test that 10 concurrent WebSocket clients receive every published event frame without drop.

    Asserts:
    - 10 concurrent WebSocket connections to the same analysis ID
    - All 10 connections receive initial status frame + all intermediate steps + terminal message
    - 0 messages dropped across all 10 connections
    - Message sequence and types are identical across all clients
    """
    db_file = f"/tmp/test_ws_{uuid.uuid4().hex}.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
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
    query = "Concurrent WebSocket broadcast test for policy data stream"

    async def init_record() -> None:
        async with session_factory() as session:
            await create_analysis(
                db=session,
                query=query,
                analysis_id=analysis_id,
                status=AnalysisStatus.RUNNING,
            )

    asyncio.run(init_record())

    client = TestClient(app)
    channel = get_channel_name(analysis_id)
    concurrency_count = 10

    # Synchronization primitives
    ready_barrier = threading.Barrier(concurrency_count + 1)
    client_results: list[list[dict[str, Any]]] = [[] for _ in range(concurrency_count)]
    client_errors: list[Exception | None] = [None for _ in range(concurrency_count)]

    def ws_client_worker(client_idx: int) -> None:
        try:
            with client.websocket_connect(f"/ws/analysis/{analysis_id}") as ws:
                # 1. First frame sent on connection accept is initial status_change
                init_frame = ws.receive_json()
                client_results[client_idx].append(init_frame)

                # Signal this client is connected and listening
                ready_barrier.wait()

                # Loop reading incoming message frames until terminal frame
                while True:
                    try:
                        frame = ws.receive_json()
                        client_results[client_idx].append(frame)
                        f_type = str(frame.get("type", "")).upper()
                        if f_type in ("ANALYSIS_DONE", "COMPLETE", "ERROR", "ANALYSIS_ERROR"):
                            break
                    except Exception as loop_err:
                        client_errors[client_idx] = loop_err
                        break
        except Exception as conn_err:
            client_errors[client_idx] = conn_err
            ready_barrier.wait()

    # Launch 10 concurrent client threads
    threads = [
        threading.Thread(target=ws_client_worker, args=(i,), daemon=True)
        for i in range(concurrency_count)
    ]
    for t in threads:
        t.start()

    # Wait for all 10 clients to connect and receive initial frame
    ready_barrier.wait(timeout=15.0)

    # Allow pubsub subscriber queues to register
    for _ in range(300):
        if in_memory_broker.subscriber_count(channel) >= concurrency_count:
            break
        time.sleep(0.02)

    assert in_memory_broker.subscriber_count(channel) >= 5, (
        f"Expected at least 5 active subscribers on {channel}, "
        f"got {in_memory_broker.subscriber_count(channel)}. Errors: {client_errors}"
    )

    # Broadcast 6 sequential agent steps + 1 terminal ANALYSIS_DONE frame
    expected_message_count = 1 + 6 + 1  # 1 initial + 6 steps + 1 done = 8 messages

    async def broadcast_events() -> None:
        # Step 1: Coordinator thinking
        await publish_step(
            analysis_id,
            format_agent_step_message(
                analysis_id, "coordinator", "THINK", {"reasoning": "Formulating research plan"}, 1
            ),
        )
        # Step 2: Coordinator plan done
        await publish_step(
            analysis_id,
            format_agent_step_message(
                analysis_id, "coordinator", "DONE", {"plan": "Search economic datasets"}, 2
            ),
        )
        # Step 3: Extraction act
        await publish_step(
            analysis_id,
            format_agent_step_message(
                analysis_id, "extraction", "ACT", {"tool": "fetch_singstat_table"}, 3
            ),
        )
        # Step 4: Extraction observe
        await publish_step(
            analysis_id,
            format_agent_step_message(analysis_id, "extraction", "OBSERVE", {"tables_found": 3}, 4),
        )
        # Step 5: Analytics calculate
        await publish_step(
            analysis_id,
            format_agent_step_message(
                analysis_id, "analytics", "ACT", {"calculation": "YoY growth analysis"}, 5
            ),
        )
        # Step 6: Analytics report
        await publish_step(
            analysis_id,
            format_agent_step_message(
                analysis_id, "analytics", "DONE", {"insights": "Positive 3.2% CAGR"}, 6
            ),
        )
        # Terminal step: ANALYSIS_DONE
        await publish_step(
            analysis_id,
            format_analysis_done_message(
                analysis_id,
                result={
                    "insights": "Comprehensive growth analysis complete.",
                    "charts": [{"chart_type": "line", "title": "GDP Growth"}],
                },
            ),
        )

    asyncio.run(broadcast_events())

    # Join threads with timeout
    for t in threads:
        t.join(timeout=10.0)

    try:
        # Validate that all 10 clients received every single message without drops
        for idx in range(concurrency_count):
            assert client_errors[idx] is None, (
                f"Client {idx} failed with error: {client_errors[idx]}"
            )
            frames = client_results[idx]
            assert len(frames) == expected_message_count, (
                f"Client {idx} received {len(frames)} frames, expected {expected_message_count}. "
                f"Types received: {[f.get('type') for f in frames]}"
            )

            # Frame 0 is status_change
            assert frames[0].get("type") in ("status_change", "STATUS_CHANGE")

            # Frames 1-6 are agent steps with strict sequence numbers 1-6
            for step_idx in range(1, 7):
                f = frames[step_idx]
                assert f.get("type") in ("agent_step", "AGENT_STEP")
                assert f.get("sequence_no") == step_idx, (
                    f"Client {idx} expected sequence_no {step_idx}, got {f.get('sequence_no')}"
                )

            # Final frame is ANALYSIS_DONE
            terminal_frame = frames[-1]
            assert terminal_frame.get("type") in (
                "ANALYSIS_DONE",
                "analysis_done",
                "complete",
                "COMPLETE",
            )
            assert terminal_frame.get("result") is not None
            assert "insights" in terminal_frame.get("result", {})

    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
        with contextlib.suppress(FileNotFoundError):
            os.remove(db_file)


def test_10_concurrent_websockets_live_pipeline_run() -> None:
    """Test 10 concurrent WebSocket clients receiving live streaming from run_analysis().

    Asserts:
    - 10 concurrent clients connect while pipeline runs
    - All 10 clients receive all live agent steps
    - All 10 clients receive final ANALYSIS_DONE message
    - Zero message dropped across all clients
    """
    db_file = f"/tmp/test_ws_{uuid.uuid4().hex}.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
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
    query = "Analyze Singapore labor productivity and median income growth 2018-2023"

    async def init_record() -> None:
        async with session_factory() as session:
            await create_analysis(
                db=session,
                query=query,
                analysis_id=analysis_id,
                status=AnalysisStatus.PENDING,
            )

    asyncio.run(init_record())

    client = TestClient(app)
    concurrency_count = 10
    ready_barrier = threading.Barrier(concurrency_count + 1)
    client_results: list[list[dict[str, Any]]] = [[] for _ in range(concurrency_count)]
    client_errors: list[Exception | None] = [None for _ in range(concurrency_count)]

    def ws_listener(idx: int) -> None:
        try:
            with client.websocket_connect(f"/ws/analysis/{analysis_id}") as ws:
                init_frame = ws.receive_json()
                client_results[idx].append(init_frame)
                ready_barrier.wait()

                while True:
                    try:
                        frame = ws.receive_json()
                        client_results[idx].append(frame)
                        f_type = str(frame.get("type", "")).upper()
                        if f_type in ("ANALYSIS_DONE", "COMPLETE", "ERROR", "ANALYSIS_ERROR"):
                            break
                    except Exception as e:
                        client_errors[idx] = e
                        break
        except Exception as e:
            client_errors[idx] = e
            ready_barrier.wait()

    threads = [
        threading.Thread(target=ws_listener, args=(i,), daemon=True)
        for i in range(concurrency_count)
    ]
    for t in threads:
        t.start()

    # Wait for all 10 clients to connect
    ready_barrier.wait(timeout=15.0)

    # Run analysis live in background worker thread
    def run_pipeline_worker() -> None:
        async def exec_pipeline() -> None:
            async with session_factory() as session:
                await run_analysis(
                    analysis_id=analysis_id,
                    query=query,
                    db=session,
                )

        asyncio.run(exec_pipeline())

    pipeline_thread = threading.Thread(target=run_pipeline_worker)
    pipeline_thread.start()
    pipeline_thread.join(timeout=20.0)

    for t in threads:
        t.join(timeout=10.0)

    try:
        # Verify all 10 received messages and terminal frame
        for idx in range(concurrency_count):
            assert client_errors[idx] is None, f"Client {idx} failed: {client_errors[idx]}"
            frames = client_results[idx]
            # Must have at least initial frame + 3 agent steps + terminal ANALYSIS_DONE >= 5 frames
            assert len(frames) >= 5, (
                f"Client {idx} received only {len(frames)} frames. "
                f"Frames: {[f.get('type') for f in frames]}"
            )

            # Final frame is ANALYSIS_DONE
            terminal_frame = frames[-1]
            assert terminal_frame.get("type") in ("ANALYSIS_DONE", "complete"), (
                f"Client {idx} last frame was {terminal_frame.get('type')}"
            )
            assert terminal_frame.get("result") is not None

        # Verify that all 10 clients received exactly the same frame count (0 dropped)
        frame_counts = [len(r) for r in client_results]
        assert len(set(frame_counts)) == 1, (
            f"Inconsistent frame counts across clients (dropped messages detected): {frame_counts}"
        )

    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
        with contextlib.suppress(FileNotFoundError):
            os.remove(db_file)
