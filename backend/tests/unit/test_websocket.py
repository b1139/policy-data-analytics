"""Unit and integration tests for WebSocket streaming, Pub/Sub, and connection lifecycle."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base, get_db
from app.crud.analysis import create_analysis
from app.main import app
from app.schemas.analysis import AnalysisStatus
from app.schemas.websocket import WSMessageType
from app.services.analysis_service import AnalysisService
from app.services.pubsub import (
    CHANNEL_CLOSE_SENTINEL,
    InMemoryPubSub,
    format_agent_step_message,
    format_complete_message,
    format_error_message,
    format_status_change_message,
    format_ws_message,
    get_channel_name,
    in_memory_broker,
    publish_step,
    reset_redis_availability_cache,
)


@pytest.fixture(autouse=True)
def _clear_redis_cache():
    """Reset cached Redis availability before and after every test."""
    reset_redis_availability_cache()
    yield
    reset_redis_availability_cache()


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite database session."""
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


@pytest.fixture(autouse=True)
def reset_broker_state() -> None:
    """Clear active in-memory broker subscribers and reset health cache."""
    asyncio.run(in_memory_broker.clear_all())


# ==============================================================================
# 1. Pub/Sub Broker Unit Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_in_memory_pubsub_single_subscriber() -> None:
    """In-memory broker delivers message to a single active subscriber."""
    broker = InMemoryPubSub()
    channel = "analysis:test-1:steps"

    queue = await broker.subscribe(channel)
    assert broker.subscriber_count(channel) == 1

    payload = json.dumps({"type": "agent_step", "step": 1})
    count = await broker.publish(channel, payload)
    assert count == 1

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received == payload

    await broker.unsubscribe(channel, queue)
    assert broker.subscriber_count(channel) == 0


@pytest.mark.asyncio
async def test_in_memory_pubsub_multiple_subscribers() -> None:
    """In-memory broker broadcasts messages to multiple simultaneous subscribers."""
    broker = InMemoryPubSub()
    channel = "analysis:test-multi:steps"

    q1 = await broker.subscribe(channel)
    q2 = await broker.subscribe(channel)
    q3 = await broker.subscribe(channel)
    assert broker.subscriber_count(channel) == 3

    payload = json.dumps({"type": "broadcast", "data": "hello"})
    count = await broker.publish(channel, payload)
    assert count == 3

    m1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    m2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    m3 = await asyncio.wait_for(q3.get(), timeout=1.0)

    assert m1 == payload
    assert m2 == payload
    assert m3 == payload

    await broker.close_channel(channel)
    assert await asyncio.wait_for(q1.get(), timeout=1.0) == CHANNEL_CLOSE_SENTINEL
    assert await asyncio.wait_for(q2.get(), timeout=1.0) == CHANNEL_CLOSE_SENTINEL
    assert await asyncio.wait_for(q3.get(), timeout=1.0) == CHANNEL_CLOSE_SENTINEL


@pytest.mark.asyncio
async def test_publish_step_in_memory_fallback() -> None:
    """publish_step delivers message via in-memory broker when Redis is down."""
    analysis_id = uuid.uuid4()
    channel = get_channel_name(analysis_id)
    queue = await in_memory_broker.subscribe(channel)

    step = {
        "agent": "coordinator",
        "step_type": "THINK",
        "sequence_no": 1,
        "content": {"reasoning": "Formulating research plan"},
    }

    with patch("app.services.pubsub.is_redis_available", return_value=False):
        await publish_step(analysis_id, step)

    raw_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    parsed = json.loads(raw_msg)

    assert parsed["type"] == "agent_step"
    assert parsed["analysis_id"] == str(analysis_id)
    assert parsed["agent"] == "coordinator"
    assert parsed["step_type"] == "THINK"
    assert parsed["sequence_no"] == 1
    assert parsed["content"]["reasoning"] == "Formulating research plan"
    assert "timestamp" in parsed


@pytest.mark.asyncio
async def test_publish_step_terminal_message_closes_channel() -> None:
    """Publishing complete or error message automatically closes in-memory channel."""
    analysis_id = uuid.uuid4()
    channel = get_channel_name(analysis_id)
    queue = await in_memory_broker.subscribe(channel)

    complete_step = {
        "type": "complete",
        "result": {"insights": "Trend analysis complete"},
    }

    with patch("app.services.pubsub.is_redis_available", return_value=False):
        await publish_step(analysis_id, complete_step)

    msg1 = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert json.loads(msg1)["type"] == "complete"

    sentinel = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert sentinel == CHANNEL_CLOSE_SENTINEL


@pytest.mark.asyncio
async def test_publish_step_redis_delivery() -> None:
    """publish_step publishes to Redis when Redis client is available."""
    analysis_id = uuid.uuid4()
    mock_redis = AsyncMock()

    with (
        patch("app.services.pubsub.get_redis_client", return_value=mock_redis),
        patch("app.services.pubsub.is_redis_available", return_value=True),
    ):
        await publish_step(
            analysis_id,
            {"type": "agent_step", "step_type": "ACT", "content": {"tool": "singstat"}},
        )

    mock_redis.publish.assert_called_once()
    args, _ = mock_redis.publish.call_args
    assert args[0] == get_channel_name(analysis_id)
    payload = json.loads(args[1])
    assert payload["type"] == "agent_step"
    assert payload["analysis_id"] == str(analysis_id)


# ==============================================================================
# 2. Message Format Schema Verification (LLD.md §7)
# ==============================================================================


def test_format_ws_message_structure() -> None:
    """format_ws_message returns expected schema keys and ISO timestamp."""
    aid = uuid.uuid4()
    msg = format_ws_message(
        analysis_id=aid,
        message_type="agent_step",
        data={"note": "processing"},
        agent="extraction",
        step_type="ACT",
    )
    assert msg["type"] == "agent_step"
    assert msg["analysis_id"] == str(aid)
    assert isinstance(msg["timestamp"], str)
    assert msg["data"]["note"] == "processing"
    assert msg["agent"] == "extraction"
    assert msg["step_type"] == "ACT"


def test_format_agent_step_message_lld_compliance() -> None:
    """format_agent_step_message conforms exactly to LLD §7 AGENT_STEP schema."""
    aid = uuid.uuid4()
    content = {"reasoning": "Fetching SingStat data", "tool_call": None}
    msg = format_agent_step_message(
        analysis_id=aid,
        agent_name="coordinator",
        step_type="THINK",
        content=content,
        sequence_no=3,
    )
    assert msg["type"] == WSMessageType.AGENT_STEP.value
    assert msg["analysis_id"] == str(aid)
    assert msg["agent"] == "coordinator"
    assert msg["step_type"] == "THINK"
    assert msg["sequence_no"] == 3
    assert msg["content"] == content
    assert "timestamp" in msg


def test_format_complete_message_lld_compliance() -> None:
    """format_complete_message conforms exactly to LLD §7 ANALYSIS_DONE schema."""
    aid = uuid.uuid4()
    result = {
        "insights": "Employment grew 18%",
        "charts": [{"data": []}],
        "citations": [{"source": "SingStat"}],
    }
    msg = format_complete_message(analysis_id=aid, result=result)
    assert msg["type"] == WSMessageType.COMPLETE.value
    assert msg["analysis_id"] == str(aid)
    assert msg["result"] == result
    assert msg["data"]["result"] == result


def test_format_error_message_structure() -> None:
    """format_error_message formats error payload with error field."""
    aid = uuid.uuid4()
    msg = format_error_message(analysis_id=aid, error="Dataset unavailable")
    assert msg["type"] == WSMessageType.ERROR.value
    assert msg["analysis_id"] == str(aid)
    assert msg["error"] == "Dataset unavailable"


def test_format_status_change_message_structure() -> None:
    """format_status_change_message formats status_change payload."""
    aid = uuid.uuid4()
    msg = format_status_change_message(analysis_id=aid, status="RUNNING")
    assert msg["type"] == WSMessageType.STATUS_CHANGE.value
    assert msg["analysis_id"] == str(aid)
    assert msg["data"]["status"] == "RUNNING"


# ==============================================================================
# 3. WebSocket Endpoint Connection Lifecycle Tests
# ==============================================================================


class MockDBResult:
    """Mock query result container for scalar_one_or_none inspection."""

    def __init__(self, record: object) -> None:
        self._record = record

    def scalar_one_or_none(self) -> object:
        return self._record


class MockDBSession:
    """Mock AsyncSession implementing execute for CRUD isolation."""

    def __init__(self, record: object) -> None:
        self._record = record

    async def execute(self, stmt: object) -> MockDBResult:  # noqa: ARG002
        return MockDBResult(self._record)


def test_ws_invalid_analysis_uuid() -> None:
    """WebSocket connection with invalid UUID string receives error frame and closes."""
    test_client = TestClient(app)
    with test_client.websocket_connect("/ws/analysis/invalid-uuid-string") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Invalid analysis UUID" in msg["data"]["error"]


def test_ws_non_existent_analysis() -> None:
    """WebSocket connection to non-existent analysis receives error frame and closes."""
    non_existent_id = uuid.uuid4()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(None)  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        with test_client.websocket_connect(f"/ws/analysis/{non_existent_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Analysis not found" in msg["data"]["error"]
    finally:
        app.dependency_overrides.clear()


def test_ws_already_completed_analysis() -> None:
    """WebSocket connection to already completed analysis sends complete frame and closes."""
    aid = uuid.uuid4()

    class CompletedAnalysis:
        id = aid
        status = AnalysisStatus.DONE
        result = {"insights": "Historical completed result"}
        error_msg = None

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(CompletedAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        with test_client.websocket_connect(f"/ws/analysis/{aid}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "complete"
            assert msg["result"]["insights"] == "Historical completed result"
    finally:
        app.dependency_overrides.clear()


def test_ws_already_failed_analysis() -> None:
    """WebSocket connection to already failed analysis sends error frame and closes."""
    aid = uuid.uuid4()

    class FailedAnalysis:
        id = aid
        status = AnalysisStatus.FAILED
        result = None
        error_msg = "Upstream provider timeout"

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(FailedAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        with test_client.websocket_connect(f"/ws/analysis/{aid}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["error"] == "Upstream provider timeout"
    finally:
        app.dependency_overrides.clear()


def test_ws_streaming_agent_steps_verbatim() -> None:
    """WebSocket client connects, receives initial frame, and streams steps verbatim."""
    aid = uuid.uuid4()

    class RunningAnalysis:
        id = aid
        status = AnalysisStatus.RUNNING
        result = None
        error_msg = None

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(RunningAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        with test_client.websocket_connect(f"/ws/analysis/{aid}") as ws:
            # 1. Initial status connection message
            init_frame = ws.receive_json()
            assert init_frame["type"] == "status_change"
            assert init_frame["data"]["status"] == AnalysisStatus.RUNNING

            # Wait for subscriber registration
            channel = get_channel_name(aid)
            for _ in range(50):
                if in_memory_broker.subscriber_count(channel) >= 1:
                    break
                time.sleep(0.02)

            # 2. Publish an agent step
            step_payload = format_agent_step_message(
                analysis_id=aid,
                agent_name="extraction",
                step_type="ACT",
                content={"tool": "singstat_fetch", "dataset": "table_m1234"},
                sequence_no=1,
            )
            asyncio.run(publish_step(aid, step_payload))

            step_frame = ws.receive_json()
            assert step_frame["type"] == "agent_step"
            assert step_frame["agent"] == "extraction"
            assert step_frame["step_type"] == "ACT"
            assert step_frame["sequence_no"] == 1
            assert step_frame["content"]["dataset"] == "table_m1234"

            # 3. Publish completion
            complete_payload = format_complete_message(
                analysis_id=aid,
                result={"summary": "Successfully analyzed SingStat data"},
            )
            asyncio.run(publish_step(aid, complete_payload))

            complete_frame = ws.receive_json()
            assert complete_frame["type"] == "complete"
            assert complete_frame["result"]["summary"] == "Successfully analyzed SingStat data"
    finally:
        app.dependency_overrides.clear()


def test_ws_multiple_simultaneous_connections() -> None:
    """Multiple simultaneous WebSocket clients to same analysis all receive steps."""
    aid = uuid.uuid4()

    class RunningAnalysis:
        id = aid
        status = AnalysisStatus.RUNNING
        result = None
        error_msg = None

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(RunningAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        with (
            test_client.websocket_connect(f"/ws/analysis/{aid}") as ws1,
            test_client.websocket_connect(f"/ws/analysis/{aid}") as ws2,
        ):
            # Both receive initial connect message
            init1 = ws1.receive_json()
            init2 = ws2.receive_json()
            assert init1["type"] == "status_change"
            assert init2["type"] == "status_change"

            # Wait for both subscribers to register
            channel = get_channel_name(aid)
            for _ in range(50):
                if in_memory_broker.subscriber_count(channel) >= 2:
                    break
                time.sleep(0.02)

            # Publish broadcast step
            step_payload = format_agent_step_message(
                analysis_id=aid,
                agent_name="analytics",
                step_type="DONE",
                content={"status": "Computed regressions"},
                sequence_no=2,
            )
            asyncio.run(publish_step(aid, step_payload))

            # Both clients receive the step
            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            assert msg1["type"] == "agent_step"
            assert msg2["type"] == "agent_step"
            assert msg1["sequence_no"] == 2
            assert msg2["sequence_no"] == 2
    finally:
        app.dependency_overrides.clear()


def test_ws_keepalive_ping_loop() -> None:
    """WebSocket server sends keepalive ping message within configured interval."""
    aid = uuid.uuid4()

    class RunningAnalysis:
        id = aid
        status = AnalysisStatus.RUNNING
        result = None
        error_msg = None

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(RunningAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        # Configure small ping_interval (0.05s) to test keepalive without sleeping 60s
        with test_client.websocket_connect(f"/ws/analysis/{aid}?ping_interval=0.05") as ws:
            init_frame = ws.receive_json()
            assert init_frame["type"] == "status_change"

            ping_frame = ws.receive_json()
            assert ping_frame["type"] == WSMessageType.PING.value
            assert ping_frame["analysis_id"] == str(aid)
            assert "timestamp" in ping_frame
    finally:
        app.dependency_overrides.clear()


def test_ws_client_disconnect_clean_handling() -> None:
    """Client disconnect closes subscription cleanly without errors."""
    aid = uuid.uuid4()

    class RunningAnalysis:
        id = aid
        status = AnalysisStatus.RUNNING
        result = None
        error_msg = None

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield MockDBSession(RunningAnalysis())  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        test_client = TestClient(app)
        channel = get_channel_name(aid)

        with test_client.websocket_connect(f"/ws/analysis/{aid}") as ws:
            _ = ws.receive_json()
            ws.close()

        time.sleep(0.05)
        # Active subscriber count drops back to 0
        assert in_memory_broker.subscriber_count(channel) == 0
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. AnalysisService Helper Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_analysis_service_publish_step() -> None:
    """AnalysisService.publish_step delegates properly to pubsub."""
    aid = uuid.uuid4()
    channel = get_channel_name(aid)
    q = await in_memory_broker.subscribe(channel)

    step = {"type": "agent_step", "sequence_no": 1, "data": {"note": "service test"}}
    await AnalysisService.publish_step(aid, step)

    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert json.loads(received)["sequence_no"] == 1


@pytest.mark.asyncio
async def test_analysis_service_run_pipeline_sets_running(async_db: AsyncSession) -> None:
    """AnalysisService.run_pipeline transitions analysis to RUNNING and dispatches event."""
    analysis = await create_analysis(
        db=async_db,
        query="Pipeline background test",
        status=AnalysisStatus.PENDING,
    )

    channel = get_channel_name(analysis.id)
    q = await in_memory_broker.subscribe(channel)

    async def fake_run_analysis(analysis_id, db=None, **kwargs):  # noqa: ARG001
        await publish_step(
            analysis_id, format_status_change_message(analysis_id, AnalysisStatus.RUNNING)
        )
        return {"status": "done"}

    with (
        patch("app.services.analysis_service.async_session_factory") as mock_session_factory,
        patch("app.agents.graph.run_analysis", side_effect=fake_run_analysis),
    ):
        mock_session_factory.return_value.__aenter__.return_value = async_db
        mock_session_factory.return_value.__aexit__.return_value = None

        await AnalysisService.run_pipeline(analysis.id)

    # Status update was published
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    parsed = json.loads(event)
    assert parsed["type"] == "status_change"
    assert parsed["data"]["status"] == AnalysisStatus.RUNNING
