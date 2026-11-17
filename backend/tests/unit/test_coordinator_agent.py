"""Unit tests for Coordinator Agent node, query parsing, LLM routing, and fallback planning."""

import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.coordinator import (
    coordinator_db_context,
    coordinator_node,
    detect_sectors_from_query,
    detect_topics_from_query,
    extract_years_from_query,
    generate_rule_based_plan,
)
from app.agents.graph import build_graph
from app.agents.state import AgentName, AgentState, StepType, create_initial_state
from app.core.database import Base
from app.llm.base import LLMResponse
from app.models.agent_log import AgentLog
from app.models.analysis import Analysis


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


def test_extract_years_from_query():
    """Verify regex extraction of year ranges and single years."""
    # Dash range
    assert extract_years_from_query("Tech hiring 2018-2023") == ("2018", "2023")
    # 'to' range
    assert extract_years_from_query("Policy shifts 2015 to 2020") == ("2015", "2020")
    # Multiple years in text
    assert extract_years_from_query("Comparing 2024 and 2019 indicators") == ("2019", "2024")
    # Single year
    assert extract_years_from_query("Singapore inflation in 2022") == ("2022", "2022")
    # Default fallback when no years present
    assert extract_years_from_query("General Singapore workforce overview") in (
        ("2019", "2024"),
        ("2019", "2025"),
    )


def test_detect_sectors_from_query():
    """Verify sector detection against Singapore economic categories."""
    assert "Technology" in detect_sectors_from_query("Analyze software and AI hiring in Singapore")
    assert "Finance" in detect_sectors_from_query("Banking and fintech headcount changes")
    assert "Manufacturing" in detect_sectors_from_query("Semiconductor factory output")
    assert "Healthcare" in detect_sectors_from_query("Hospital and biomedical workforce")
    assert "Construction" in detect_sectors_from_query("Real estate and infrastructure building")

    # Fallback default sectors
    defaults = detect_sectors_from_query("General national indicators")
    assert "General Economy" in defaults


def test_detect_topics_from_query():
    """Verify policy topic extraction from queries."""
    assert "employment" in detect_topics_from_query("Workforce retrenchment and job creation")
    assert "wages" in detect_topics_from_query("Median monthly salaries and compensation")
    assert "gdp" in detect_topics_from_query("Singapore GDP economic growth")
    assert "inflation" in detect_topics_from_query("Consumer price index and inflation")

    # Fallback default topics
    defaults = detect_topics_from_query("Overview of trends")
    assert "employment" in defaults


def test_generate_rule_based_plan():
    """Verify deterministic fallback plan formulation."""
    query = "Analyze tech and finance employment in Singapore 2020-2024"
    plan = generate_rule_based_plan(query)

    assert plan["date_range"] == ("2020", "2024")
    assert plan["time_period"] == "2020-2024"
    assert "Technology" in plan["target_sectors"]
    assert "Finance" in plan["target_sectors"]
    assert "employment" in plan["topics"]
    assert "singstat" in plan["sources"]
    assert "datagov" in plan["sources"]
    assert len(plan["sub_tasks"]) >= 2
    assert len(plan["planned_datasets"]) >= 2
    assert len(plan["required_metrics"]) > 0


@pytest.mark.asyncio
async def test_coordinator_node_llm_success():
    """Verify coordinator_node with mocked LLMRouter returning structured JSON."""
    analysis_id = str(uuid.uuid4())
    state: AgentState = create_initial_state(
        analysis_id=analysis_id,
        query="Technology sector workforce trends 2019-2024",
    )

    sample_plan_json = {
        "query_intent": "Analyze ICT employment and tech headcount trends",
        "target_sectors": ["Technology"],
        "time_period": "2019-2024",
        "required_metrics": ["headcount", "employment_growth"],
        "sources": ["singstat", "datagov"],
        "topics": ["employment", "technology"],
        "date_range": ["2019", "2024"],
        "sub_tasks": [
            "Fetch employment by industry 2019-2024 from SingStat",
            "Fetch ICT headcount from Data.gov.sg",
        ],
        "planned_datasets": [
            {"source": "singstat", "dataset_id": "M810361", "title": "SingStat ICT Table"}
        ],
    }

    mock_response = LLMResponse(
        content=json.dumps(sample_plan_json),
        model="gemini-2.5-flash",
        provider="gemini",
        latency_ms=120.0,
    )

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(return_value=mock_response)

    published_steps: list[dict] = []

    async def mock_publish(_aid: str, step: dict) -> None:
        published_steps.append(step)

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", side_effect=mock_publish),
    ):
        result_state = await coordinator_node(state)

    # Validate state mutations
    assert result_state["current_agent"] == AgentName.COORDINATOR
    assert result_state["status"] == "planned"
    assert result_state["research_plan"] is not None
    assert (
        result_state["research_plan"]["query_intent"]
        == "Analyze ICT employment and tech headcount trends"
    )
    assert result_state["research_plan"]["date_range"] == ("2019", "2024")
    assert result_state["research_plan"]["sources"] == ["singstat", "datagov"]
    assert len(result_state["research_plan"]["sub_tasks"]) == 2

    # Validate emitted steps
    assert len(result_state["agent_logs"]) == 2
    think_log = result_state["agent_logs"][0]
    done_log = result_state["agent_logs"][1]

    assert think_log["step_type"] == StepType.THINK
    assert think_log["sequence_no"] == 1
    assert done_log["step_type"] == StepType.DONE
    assert done_log["sequence_no"] == 2

    # Validate pubsub deliveries
    assert len(published_steps) == 2
    assert published_steps[0]["step_type"] == "THINK"
    assert published_steps[1]["step_type"] == "DONE"

    # Validate router call parameters
    mock_router.complete.assert_awaited_once()
    _, kwargs = mock_router.complete.call_args
    assert kwargs.get("temperature") in (0.2, 0.3)
    assert kwargs.get("json_mode") is True


@pytest.mark.asyncio
async def test_coordinator_node_markdown_code_block_json():
    """Verify coordinator_node correctly parses JSON wrapped in markdown triple backticks."""
    analysis_id = str(uuid.uuid4())
    state: AgentState = create_initial_state(
        analysis_id=analysis_id,
        query="Healthcare employment 2021-2023",
    )

    raw_json = json.dumps(
        {
            "query_intent": "Healthcare labor changes",
            "target_sectors": ["Healthcare"],
            "time_period": "2021-2023",
            "required_metrics": ["headcount"],
            "sources": ["singstat"],
            "topics": ["employment"],
            "date_range": ["2021", "2023"],
            "sub_tasks": ["Fetch healthcare tables from SingStat"],
            "planned_datasets": [{"source": "singstat", "dataset_id": "M810361"}],
        }
    )
    wrapped_content = f"```json\n{raw_json}\n```"

    mock_response = LLMResponse(
        content=wrapped_content,
        model="mock-bedrock",
        provider="bedrock",
        latency_ms=95.0,
    )

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(return_value=mock_response)

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
    ):
        result_state = await coordinator_node(state)

    assert result_state["research_plan"]["target_sectors"] == ["Healthcare"]
    assert result_state["research_plan"]["date_range"] == ("2021", "2023")


@pytest.mark.asyncio
async def test_coordinator_node_llm_failure_fallback():
    """Verify fallback parser engages when LLM router raises an exception."""
    analysis_id = str(uuid.uuid4())
    state: AgentState = create_initial_state(
        analysis_id=analysis_id,
        query="Singapore manufacturing and electronics employment 2019-2024",
    )

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(side_effect=RuntimeError("Primary & Fallback LLM failed"))

    published_steps: list[dict] = []

    async def mock_publish(_aid: str, step: dict) -> None:
        published_steps.append(step)

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", side_effect=mock_publish),
    ):
        result_state = await coordinator_node(state)

    # Must not crash, status planned
    assert result_state["current_agent"] == AgentName.COORDINATOR
    assert result_state["status"] == "planned"

    # Verify fallback plan
    plan = result_state["research_plan"]
    assert plan is not None
    assert "Manufacturing" in plan["target_sectors"]
    assert plan["date_range"] == ("2019", "2024")
    assert plan["time_period"] == "2019-2024"
    assert "singstat" in plan["sources"]
    assert len(plan["sub_tasks"]) >= 2

    # Steps were still emitted
    assert len(result_state["agent_logs"]) == 2
    assert result_state["agent_logs"][0]["step_type"] == StepType.THINK
    assert result_state["agent_logs"][1]["step_type"] == StepType.DONE
    assert len(published_steps) == 2


@pytest.mark.asyncio
async def test_coordinator_node_invalid_json_fallback():
    """Verify fallback parser engages when LLM produces invalid/unparseable JSON."""
    analysis_id = str(uuid.uuid4())
    state: AgentState = create_initial_state(
        analysis_id=analysis_id,
        query="Finance sector trends from 2020 to 2023",
    )

    mock_response = LLMResponse(
        content="Sorry, I cannot produce JSON right now: {broken json...",
        model="mock-gemini",
        provider="gemini",
    )

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(return_value=mock_response)

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
    ):
        result_state = await coordinator_node(state)

    plan = result_state["research_plan"]
    assert plan is not None
    assert "Finance" in plan["target_sectors"]
    assert plan["date_range"] == ("2020", "2023")


@pytest.mark.asyncio
async def test_coordinator_node_database_logging(async_db: AsyncSession):
    """Verify THINK and DONE steps are persisted into the AgentLog database table."""
    analysis_uuid = uuid.uuid4()
    parent_analysis = Analysis(
        id=analysis_uuid,
        query="Technology sector salaries 2019-2024",
        status="running",
    )
    async_db.add(parent_analysis)
    await async_db.commit()

    state: AgentState = create_initial_state(
        analysis_id=str(analysis_uuid),
        query="Technology sector salaries 2019-2024",
    )

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "query_intent": "Analyze tech salaries",
                    "target_sectors": ["Technology"],
                    "time_period": "2019-2024",
                    "required_metrics": ["median_income"],
                    "sources": ["singstat", "datagov"],
                    "topics": ["wages"],
                    "date_range": ["2019", "2024"],
                    "sub_tasks": ["Fetch wages from SingStat"],
                    "planned_datasets": [{"source": "singstat", "dataset_id": "M810361"}],
                }
            ),
            model="mock",
            provider="mock",
        )
    )

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
    ):
        await coordinator_node(state, db=async_db)

    # Query DB logs
    result = await async_db.execute(
        select(AgentLog).where(AgentLog.analysis_id == analysis_uuid).order_by(AgentLog.sequence_no)
    )
    logs = list(result.scalars().all())

    assert len(logs) == 2
    assert logs[0].step_type == "THINK"
    assert logs[0].sequence_no == 1
    assert logs[0].agent_name == "coordinator"

    assert logs[1].step_type == "DONE"
    assert logs[1].sequence_no == 2
    assert logs[1].agent_name == "coordinator"
    assert "plan" in logs[1].content


@pytest.mark.asyncio
async def test_coordinator_node_with_contextvar_db(async_db: AsyncSession):
    """Verify DB session can be provided via ContextVar instead of direct argument."""
    analysis_uuid = uuid.uuid4()
    parent_analysis = Analysis(
        id=analysis_uuid,
        query="Retail and hospitality workforce 2020",
        status="running",
    )
    async_db.add(parent_analysis)
    await async_db.commit()

    state: AgentState = create_initial_state(
        analysis_id=str(analysis_uuid),
        query="Retail and hospitality workforce 2020",
    )

    token = coordinator_db_context.set(async_db)
    try:
        mock_router = AsyncMock()
        mock_router.primary_name = "mock"
        mock_router.primary = AsyncMock()
        mock_router.primary.model = "gemini-1.5-flash"
        mock_router.complete = AsyncMock(side_effect=RuntimeError("Fallback triggers"))

        with (
            patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
            patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
        ):
            await coordinator_node(state)

        result = await async_db.execute(
            select(AgentLog)
            .where(AgentLog.analysis_id == analysis_uuid)
            .order_by(AgentLog.sequence_no)
        )
        logs = list(result.scalars().all())
        assert len(logs) == 2
        assert logs[0].step_type == "THINK"
        assert logs[1].step_type == "DONE"
    finally:
        coordinator_db_context.reset(token)


@pytest.mark.asyncio
async def test_coordinator_node_in_compiled_graph(monkeypatch: pytest.MonkeyPatch):
    """Verify build_graph registers and executes coordinator_node seamlessly."""
    monkeypatch.setattr("app.core.config.settings.USE_MOCK_DATA_AS_FALLBACK", True)
    analysis_id = str(uuid.uuid4())
    initial_state = create_initial_state(
        analysis_id=analysis_id,
        query="Singapore manufacturing and AI workforce 2021-2024",
    )

    graph = build_graph()

    mock_router = AsyncMock()
    mock_router.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "query_intent": "Analyze manufacturing AI workforce",
                    "target_sectors": ["Manufacturing", "Technology"],
                    "time_period": "2021-2024",
                    "required_metrics": ["headcount"],
                    "sources": ["singstat", "datagov"],
                    "topics": ["employment"],
                    "date_range": ["2021", "2024"],
                    "sub_tasks": ["Fetch manufacturing data from SingStat"],
                    "planned_datasets": [{"source": "singstat", "dataset_id": "M810361"}],
                }
            ),
            model="mock",
            provider="mock",
        )
    )

    with (
        patch("app.agents.coordinator.get_llm_router", return_value=mock_router),
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
    ):
        final_state = await graph.ainvoke(initial_state)

    assert final_state["research_plan"] is not None
    assert "Manufacturing" in final_state["research_plan"]["target_sectors"]
    assert final_state["research_plan"]["date_range"] == ("2021", "2024")
    assert any(log["agent_name"] == "coordinator" for log in final_state["agent_logs"])
