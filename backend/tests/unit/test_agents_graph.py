"""Unit tests for LangGraph multi-agent setup, state schemas, and graph routing."""

from typing import Any

import pytest
from langgraph.graph import END
try:
    from langgraph.graph.state import CompiledStateGraph as CompiledGraph
except ImportError:
    try:
        from langgraph.graph.state import CompiledGraph  # type: ignore[attr-defined]
    except ImportError:
        from langgraph.graph.graph import CompiledGraph  # type: ignore[assignment]

from app.agents import (
    AgentName,
    AgentState,
    AgentStep,
    ResearchPlan,
    StepType,
    build_graph,
    create_initial_state,
    route_after_extraction,
    run_analysis,
)


def test_agent_state_schema():
    """Verify AgentState TypedDict contains all required fields from LLD.md §3."""
    expected_fields = {
        "analysis_id",
        "query",
        "research_plan",
        "selected_datasets",
        "raw_data",
        "statistical_results",
        "insights",
        "citations",
        "agent_logs",
        "current_agent",
        "extraction_errors",
        "final_report",
        "status",
    }
    actual_fields = set(AgentState.__annotations__.keys())
    assert expected_fields == actual_fields, (
        f"Missing or extra fields in AgentState: {expected_fields ^ actual_fields}"
    )


def test_research_plan_schema():
    """Verify ResearchPlan TypedDict contains all required specification fields."""
    expected_fields = {
        "query_intent",
        "target_sectors",
        "time_period",
        "required_metrics",
        "planned_datasets",
        "sources",
        "topics",
        "date_range",
        "time_filter",
        "recommended_chart",
        "shrink_instructions",
        "sub_tasks",
    }
    actual_fields = set(ResearchPlan.__annotations__.keys())
    assert expected_fields == actual_fields, (
        f"Missing or extra fields in ResearchPlan: {expected_fields ^ actual_fields}"
    )


def test_agent_step_and_enums():
    """Verify StepType, AgentName enums, and AgentStep TypedDict."""
    assert StepType.THINK == "THINK"
    assert StepType.ACT == "ACT"
    assert StepType.OBSERVE == "OBSERVE"
    assert StepType.DONE == "DONE"
    assert StepType.ERROR == "ERROR"

    assert AgentName.COORDINATOR == "coordinator"
    assert AgentName.EXTRACTION == "extraction"
    assert AgentName.ANALYTICS == "analytics"

    step: AgentStep = {
        "agent_name": AgentName.COORDINATOR,
        "step_type": StepType.THINK,
        "content": {"thought": "Decomposing query"},
        "sequence_no": 1,
    }
    assert step["agent_name"] == "coordinator"
    assert step["sequence_no"] == 1


def test_create_initial_state():
    """Verify create_initial_state generates complete default state."""
    state = create_initial_state(analysis_id="test-analysis-123", query="Singapore GDP growth 2023")

    assert state["analysis_id"] == "test-analysis-123"
    assert state["query"] == "Singapore GDP growth 2023"
    assert state["research_plan"] is None
    assert state["selected_datasets"] == []
    assert state["raw_data"] == {}
    assert state["statistical_results"] == {}
    assert state["insights"] == []
    assert state["citations"] == []
    assert state["agent_logs"] == []
    assert state["current_agent"] == ""
    assert state["extraction_errors"] == []
    assert state["final_report"] is None
    assert state["status"] == "pending"


def test_build_graph_compilation_and_nodes():
    """Verify build_graph returns a compiled LangGraph instance with registered nodes."""
    graph = build_graph()
    assert isinstance(graph, CompiledGraph)

    # Validate node names present in graph
    node_names = set(graph.nodes.keys())
    assert "coordinator" in node_names
    assert "extraction" in node_names
    assert "analytics" in node_names


def test_route_after_extraction():
    """Verify routing logic after extraction node."""
    # 0 errors -> analytics
    state_0 = {"extraction_errors": []}
    assert route_after_extraction(state_0) == "analytics"

    # 1 error -> analytics
    state_1 = {"extraction_errors": ["Fetch failed for table X"]}
    assert route_after_extraction(state_1) == "analytics"

    # 2 errors -> analytics (threshold is > 2)
    state_2 = {"extraction_errors": ["Error 1", "Error 2"]}
    assert route_after_extraction(state_2) == "analytics"

    # 3 errors -> END (exceeds retry threshold)
    state_3 = {"extraction_errors": ["Error 1", "Error 2", "Error 3"]}
    assert route_after_extraction(state_3) == END

    # 4 errors -> END
    state_4 = {"extraction_errors": ["Error 1", "Error 2", "Error 3", "Error 4"]}
    assert route_after_extraction(state_4) == END


@pytest.mark.asyncio
async def test_run_analysis_success_flow():
    """Verify run_analysis executes end-to-end through coordinator -> extraction -> analytics."""
    visited_nodes: list[str] = []

    async def mock_coordinator(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("coordinator")
        return {
            "current_agent": "coordinator",
            "research_plan": {
                "query_intent": "Analyze tech employment",
                "target_sectors": ["ICT"],
                "time_period": "2020-2023",
                "required_metrics": ["headcount", "growth_rate"],
                "planned_datasets": [{"source": "singstat", "dataset_id": "M123"}],
            },
            "status": "planned",
        }

    async def mock_extraction(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("extraction")
        return {
            "current_agent": "extraction",
            "raw_data": {"employment": [100, 110, 120]},
            "extraction_errors": [],
            "status": "extracted",
        }

    async def mock_analytics(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("analytics")
        return {
            "current_agent": "analytics",
            "statistical_results": {"growth": 0.20},
            "insights": ["Employment grew by 20% over the period."],
            "status": "completed",
        }

    graph = build_graph(
        coordinator_node_fn=mock_coordinator,
        extraction_node_fn=mock_extraction,
        analytics_node_fn=mock_analytics,
    )

    result = await run_analysis(
        analysis_id="analysis-success-001",
        query="Examine ICT employment growth",
        graph=graph,
    )

    # Check node execution sequence
    assert visited_nodes == ["coordinator", "extraction", "analytics"]

    # Check state updates
    assert result["analysis_id"] == "analysis-success-001"
    assert result["current_agent"] == "analytics"
    assert result["status"] == "completed"
    assert result["statistical_results"] == {"growth": 0.20}
    assert result["insights"] == ["Employment grew by 20% over the period."]
    assert result["final_report"] is not None
    assert result["final_report"]["analysis_id"] == "analysis-success-001"
    assert result["final_report"]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_analysis_conditional_branch_errors():
    """Verify conditional branch routes to END when extraction errors exceed threshold (> 2)."""
    visited_nodes: list[str] = []

    async def mock_coordinator(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("coordinator")
        return {
            "current_agent": "coordinator",
            "status": "planned",
        }

    async def mock_extraction_failing(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("extraction")
        return {
            "current_agent": "extraction",
            "extraction_errors": [
                "Connection timeout for SingStat",
                "404 Not Found from Data.gov.sg",
                "Schema validation failed",
            ],
            "status": "extraction_failed",
        }

    async def mock_analytics(state: AgentState) -> dict[str, Any]:  # noqa: ARG001
        visited_nodes.append("analytics")
        return {
            "current_agent": "analytics",
            "status": "completed",
        }

    graph = build_graph(
        coordinator_node_fn=mock_coordinator,
        extraction_node_fn=mock_extraction_failing,
        analytics_node_fn=mock_analytics,
    )

    result = await run_analysis(
        analysis_id="analysis-failure-002",
        query="Singapore inflation and wages",
        graph=graph,
    )

    # Analytics must NOT have been visited because > 2 errors routed to END
    assert visited_nodes == ["coordinator", "extraction"]
    assert "analytics" not in visited_nodes

    assert result["analysis_id"] == "analysis-failure-002"
    assert result["current_agent"] == "extraction"
    assert result["status"] == "extraction_failed"
    assert len(result["extraction_errors"]) == 3


@pytest.mark.asyncio
async def test_run_analysis_default_stubs(monkeypatch: pytest.MonkeyPatch):
    """Verify run_analysis executes with default node implementations when mock fallback is enabled."""
    monkeypatch.setattr("app.core.config.settings.USE_MOCK_DATA_AS_FALLBACK", True)
    result = await run_analysis(
        analysis_id="default-stub-run",
        query="What is Singapore's population growth?",
    )

    assert result["analysis_id"] == "default-stub-run"
    assert result["current_agent"] == "analytics"
    assert result["status"] == "completed"
    assert result["final_report"] is not None
    assert result["final_report"]["analysis_id"] == "default-stub-run"
