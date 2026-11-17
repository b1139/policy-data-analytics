"""Unit tests for Data Extraction Agent node, data tools, ReAct loop, and error handling."""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.extraction import (
    MAX_REACT_ITERATIONS,
    create_extraction_agent,
    extraction_node,
)
from app.agents.graph import build_graph
from app.agents.state import AgentName, StepType, create_initial_state
from app.agents.tools.data_tools import (
    fetch_dataset,
    list_available_datasets,
    validate_dataframe,
)
from app.core.database import Base
from app.data_sources import MockInternalDataSource, data_source_registry
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


@pytest.fixture(autouse=True)
def ensure_mock_source_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure MockInternalDataSource is present in data_source_registry and allowed in unit tests."""
    monkeypatch.setattr("app.core.config.settings.USE_MOCK_DATA_AS_FALLBACK", True)
    mock_src = MockInternalDataSource()
    data_source_registry.register(mock_src, overwrite=True)


# ==============================================================================
# 1. Data Tools Unit Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_tool_list_available_datasets_mock() -> None:
    """list_available_datasets queries the data source registry and returns matching metadata."""
    results = await list_available_datasets.ainvoke(
        {"source": "mock_internal", "keywords": "employment"}
    )
    assert isinstance(results, list)
    assert len(results) > 0
    ids = [r["id"] for r in results]
    assert "employment_by_sector" in ids

    # Test alias resolution 'mock' -> 'mock_internal'
    alias_results = await list_available_datasets.ainvoke({"source": "mock", "keywords": "wages"})
    assert len(alias_results) > 0
    assert "median_gross_wages" in [r["id"] for r in alias_results]

    # Test direct callable invocation
    direct_res = await list_available_datasets("mock_internal", "unemployment")
    assert any("unemployment" in r["id"] for r in direct_res)


@pytest.mark.asyncio
async def test_tool_fetch_dataset_mock() -> None:
    """fetch_dataset retrieves normalized DataFrame serialized to orient='split' JSON."""
    df_json = await fetch_dataset.ainvoke(
        {"source": "mock_internal", "dataset_id": "employment_by_sector"}
    )
    assert isinstance(df_json, str)
    assert len(df_json) > 0

    # Parse and verify split structure
    parsed = json.loads(df_json)
    assert "columns" in parsed
    assert "index" in parsed
    assert "data" in parsed
    assert len(parsed["data"]) > 0

    # Verify reconstruction with pandas
    df = pd.read_json(io.StringIO(df_json), orient="split")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "sector" in df.columns
    assert "employment_count" in df.columns

    # Test direct callable invocation with alias
    direct_json = await fetch_dataset("mock", "median_gross_wages")
    assert "median_wage_sgd" in direct_json or "data" in direct_json


def test_tool_validate_dataframe_valid() -> None:
    """validate_dataframe returns passed status and quality statistics for clean data."""
    df = pd.DataFrame(
        {
            "year": [2020, 2021, 2022],
            "employment": [100.0, 105.5, 110.2],
            "sector": ["Tech", "Tech", "Tech"],
        }
    )
    df_json = df.to_json(orient="split", date_format="iso")

    report = validate_dataframe.invoke({"df_json": df_json})
    assert isinstance(report, dict)
    assert report["passed"] is True
    assert report["errors"] == []
    assert report["stats"]["row_count"] == 3
    assert report["stats"]["col_count"] == 3

    # Test direct callable
    direct_report = validate_dataframe(df_json)
    assert direct_report["passed"] is True


def test_tool_validate_dataframe_empty_and_corrupt() -> None:
    """validate_dataframe flags empty or corrupted DataFrame JSON with non-raising error report."""
    empty_report = validate_dataframe.invoke({"df_json": ""})
    assert empty_report["passed"] is False
    assert len(empty_report["errors"]) > 0

    corrupt_report = validate_dataframe.invoke({"df_json": "{not valid json}"})
    assert corrupt_report["passed"] is False
    assert len(corrupt_report["errors"]) > 0


# ==============================================================================
# 2. Extraction Node Execution Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_extraction_node_with_planned_datasets() -> None:
    """extraction_node executes data extraction for planned datasets and populates state."""
    state = create_initial_state(analysis_id=str(uuid.uuid4()), query="Tech employment 2020-2024")
    state["research_plan"] = {
        "query_intent": "Analyze tech employment",
        "target_sectors": ["Technology"],
        "time_period": "2020-2024",
        "required_metrics": ["headcount"],
        "planned_datasets": [
            {
                "source": "mock_internal",
                "dataset_id": "employment_by_sector",
                "title": "Singapore Employment by Sector",
            },
            {
                "source": "mock",
                "dataset_id": "median_gross_wages",
                "title": "Median Gross Wages",
            },
        ],
        "sources": ["mock_internal"],
        "topics": ["employment", "wages"],
        "date_range": ("2020", "2024"),
        "sub_tasks": ["Fetch employment", "Fetch wages"],
    }

    with patch("app.agents.extraction.publish_step", new_callable=AsyncMock) as mock_pub:
        result_state = await extraction_node(state)

    assert result_state["current_agent"] == AgentName.EXTRACTION
    assert len(result_state["selected_datasets"]) == 2
    assert "employment_by_sector" in result_state["raw_data"]
    assert "median_gross_wages" in result_state["raw_data"]
    assert len(result_state["raw_data"]) >= 2
    assert result_state["status"] == "extracted"
    assert result_state["extraction_errors"] == []

    # Verify pubsub invocations
    assert mock_pub.call_count >= 4


@pytest.mark.asyncio
async def test_extraction_node_with_sub_tasks_discovery() -> None:
    """extraction_node executes dataset discovery via sub_tasks when planned_datasets is omitted."""
    state = create_initial_state(analysis_id=str(uuid.uuid4()), query="Singapore workforce trends")
    state["research_plan"] = {
        "sources": ["mock_internal"],
        "topics": ["employment"],
        "date_range": ("2019", "2024"),
        "sub_tasks": [
            "Fetch employment statistics from mock_internal",
            "Fetch workforce indicators from mock_internal",
        ],
    }

    with patch("app.agents.extraction.publish_step", new_callable=AsyncMock):
        result_state = await extraction_node(state)

    assert result_state["current_agent"] == "extraction"
    assert len(result_state["selected_datasets"]) >= 1
    assert result_state["status"] == "extracted"


# ==============================================================================
# 3. Step Emissions & Telemetry Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_step_emissions_and_sequence_ordering(async_db: AsyncSession) -> None:
    """Verify ACT, OBSERVE, and DONE step emissions maintain strict sequence ordering and DB persistence."""
    analysis_uuid = uuid.uuid4()
    analysis = Analysis(
        id=analysis_uuid,
        query="Tech salaries in Singapore",
        status="pending",
    )
    async_db.add(analysis)
    await async_db.commit()

    state = create_initial_state(analysis_id=str(analysis_uuid), query="Tech salaries")
    state["research_plan"] = {
        "planned_datasets": [
            {
                "source": "mock_internal",
                "dataset_id": "median_gross_wages",
                "title": "Wages dataset",
            }
        ]
    }

    published_messages: list[dict] = []

    async def mock_publish(_channel: str, message: dict) -> None:
        published_messages.append(message)

    with patch("app.agents.extraction.publish_step", side_effect=mock_publish):
        result_state = await extraction_node(state, db=async_db)

    # 1. Verify agent_logs in state
    logs = result_state["agent_logs"]
    assert len(logs) >= 3  # At least ACT (fetch), OBSERVE (fetch), ACT (val), OBSERVE (val), DONE

    # 2. Check strict monotonic sequence ordering
    seq_numbers = [log["sequence_no"] for log in logs]
    assert seq_numbers == list(range(1, len(logs) + 1))

    # 3. Check step types contain ACT, OBSERVE, and DONE
    step_types = [log["step_type"] for log in logs]
    assert StepType.ACT in step_types
    assert StepType.OBSERVE in step_types
    assert StepType.DONE in step_types

    # 4. Check WebSocket published messages match
    assert len(published_messages) == len(logs)
    for i, msg in enumerate(published_messages):
        assert msg["analysis_id"] == str(analysis_uuid)
        assert msg["data"]["agent"] == AgentName.EXTRACTION
        assert msg["data"]["sequence_no"] == i + 1

    # 5. Check persistence to database AgentLog table
    db_logs = (
        (
            await async_db.execute(
                select(AgentLog)
                .where(AgentLog.analysis_id == analysis_uuid)
                .order_by(AgentLog.sequence_no.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(db_logs) == len(logs)
    for db_log, mem_log in zip(db_logs, logs, strict=True):
        assert db_log.sequence_no == mem_log["sequence_no"]
        assert db_log.step_type == mem_log["step_type"]
        assert db_log.agent_name == AgentName.EXTRACTION


# ==============================================================================
# 4. Error Handling and Partial Failures Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_partial_failure_continues_and_accumulates_errors() -> None:
    """When a single dataset fails to extract, the error is recorded and remaining datasets succeed."""
    state = create_initial_state(analysis_id=str(uuid.uuid4()), query="Test partial failure")
    state["research_plan"] = {
        "planned_datasets": [
            {
                "source": "mock_internal",
                "dataset_id": "invalid_dataset_9999",
                "title": "Invalid Nonexistent Dataset",
                "keywords": "nonexistent_term_xyz",
            },
            {
                "source": "mock_internal",
                "dataset_id": "employment_by_sector",
                "title": "Valid Employment Dataset",
            },
        ]
    }

    with patch("app.agents.extraction.publish_step", new_callable=AsyncMock):
        result_state = await extraction_node(state)

    # Failed dataset must be in extraction_errors
    assert len(result_state["extraction_errors"]) >= 1
    assert any("invalid_dataset_9999" in err for err in result_state["extraction_errors"])

    # Valid dataset must still be successfully extracted
    assert len(result_state["selected_datasets"]) == 1
    assert result_state["selected_datasets"][0]["dataset_id"] == "employment_by_sector"
    assert "employment_by_sector" in result_state["raw_data"]
    assert result_state["status"] == "extracted"


@pytest.mark.asyncio
async def test_max_react_iterations_guardrail() -> None:
    """ReAct loop enforces MAX_REACT_ITERATIONS to prevent infinite loops."""
    state = create_initial_state(analysis_id=str(uuid.uuid4()), query="Test iterations limit")
    # Provide 30 planned datasets (exceeding MAX_REACT_ITERATIONS=15)
    state["research_plan"] = {
        "planned_datasets": [
            {
                "source": "mock_internal",
                "dataset_id": "employment_by_sector",
                "title": f"Dataset {i}",
            }
            for i in range(30)
        ]
    }

    with patch("app.agents.extraction.publish_step", new_callable=AsyncMock):
        result_state = await extraction_node(state)

    # Tool calls should not exceed guardrail
    act_steps = [log for log in result_state["agent_logs"] if log["step_type"] == StepType.ACT]
    assert len(act_steps) <= MAX_REACT_ITERATIONS + 2


# ==============================================================================
# 5. LangGraph ReAct Agent Integration Tests
# ==============================================================================


def test_create_extraction_agent_factory() -> None:
    """create_extraction_agent compiles a valid LangGraph ReAct agent graph with data tools."""
    agent = create_extraction_agent()
    assert agent is not None
    assert hasattr(agent, "ainvoke")
    assert hasattr(agent, "invoke")


@pytest.mark.asyncio
async def test_compiled_graph_end_to_end_with_extraction() -> None:
    """Full LangGraph StateGraph executes coordinator and extraction nodes sequentially."""
    graph = build_graph()
    analysis_id = str(uuid.uuid4())
    initial_state = create_initial_state(
        analysis_id=analysis_id,
        query="Analyze employment trends in Singapore 2020-2024",
    )

    with (
        patch("app.agents.coordinator.publish_step", new_callable=AsyncMock),
        patch("app.agents.extraction.publish_step", new_callable=AsyncMock),
    ):
        final_state = await graph.ainvoke(initial_state)

    assert final_state["analysis_id"] == analysis_id
    assert final_state["research_plan"] is not None
    # Extraction should have processed datasets and updated state
    assert len(final_state["selected_datasets"]) >= 1
    assert len(final_state["raw_data"]) >= 1
    # Check logs recorded from both coordinator and extraction agents
    agent_names = {log["agent_name"] for log in final_state["agent_logs"]}
    assert AgentName.COORDINATOR in agent_names
    assert AgentName.EXTRACTION in agent_names
