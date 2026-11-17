"""Tests for structured LLM outputs and schema parsing fallbacks (Story S31).

Verifies:
1. Coordinator LLM output parses cleanly to ResearchPlan schema with all required fields present.
2. Malformed or invalid JSON triggers deterministic rule-based plan fallback without crashing.
3. Markdown-fenced JSON responses (```json ... ```) are cleanly stripped and parsed.
4. Partial JSON dictionaries with missing fields are filled with sensible defaults.
5. End-to-end coordinator_node execution with MockLLMProvider produces valid research_plan.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.coordinator import (
    _parse_and_validate_plan,
    coordinator_node,
    generate_rule_based_plan,
)
from app.agents.state import AgentName, AgentState
from app.llm.base import LLMResponse

REQUIRED_RESEARCH_PLAN_FIELDS = [
    "query_intent",
    "target_sectors",
    "time_period",
    "required_metrics",
    "planned_datasets",
    "sources",
    "topics",
    "date_range",
    "sub_tasks",
]


class TestStructuredOutput:
    """Test suite for LLM JSON output validation and resilient schema parsing."""

    def test_coordinator_llm_output_parses_to_research_plan(self):
        """Coordinator LLM output parses to ResearchPlan (all required fields present)."""
        valid_llm_json = json.dumps(
            {
                "query_intent": "Analyze resident employment trends and wage progression in Singapore",
                "target_sectors": ["Technology", "Financial Services", "Healthcare"],
                "time_period": "2019-2024",
                "required_metrics": ["employment_rate", "median_wage", "headcount"],
                "sources": ["singstat", "datagov"],
                "topics": ["employment", "income"],
                "date_range": ["2019", "2024"],
                "sub_tasks": [
                    "Extract resident employment from SingStat",
                    "Calculate 5-year CAGR and median wage",
                ],
                "planned_datasets": [
                    {
                        "source": "singstat",
                        "dataset_id": "M810361",
                        "title": "Resident Employment by Industry",
                    }
                ],
            }
        )

        plan = _parse_and_validate_plan(
            raw_json=valid_llm_json,
            query="Analyze resident employment and wages between 2019 and 2024",
        )

        assert isinstance(plan, dict)
        for field in REQUIRED_RESEARCH_PLAN_FIELDS:
            assert field in plan, f"Missing required field in parsed ResearchPlan: {field}"
            assert plan[field], f"Field '{field}' should not be empty"

        assert (
            plan["query_intent"]
            == "Analyze resident employment trends and wage progression in Singapore"
        )
        assert "singstat" in plan["sources"]
        assert len(plan["planned_datasets"]) >= 1
        assert any(ds.get("dataset_id") == "M810361" for ds in plan["planned_datasets"])
        assert plan["date_range"] == ("2019", "2024")

    def test_invalid_json_from_llm_uses_fallback_rule_based_plan_no_crash(self):
        """Invalid JSON from LLM -> fallback rule-based plan used (no crash)."""
        query = "Evaluate Singapore housing prices and resale volume"
        invalid_raw_json = "I am an AI and here is your plan: { 'query_intent': broken json ... "

        # Directly verifying parse failure triggers fallback via helper logic
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_and_validate_plan(invalid_raw_json, query)

        # Fallback generator directly produces valid ResearchPlan
        fallback_plan = generate_rule_based_plan(query)
        assert isinstance(fallback_plan, dict)
        for field in REQUIRED_RESEARCH_PLAN_FIELDS:
            assert field in fallback_plan
            assert fallback_plan[field]

        assert len(fallback_plan["planned_datasets"]) >= 1
        assert "singstat" in fallback_plan["sources"]
        assert len(fallback_plan["date_range"]) == 2

    @pytest.mark.asyncio
    async def test_coordinator_node_handles_invalid_llm_json_gracefully(self):
        """coordinator_node uses rule-based plan when LLM returns invalid JSON without crashing."""
        query = "Assess inflation and CPI trajectories across Singapore"
        initial_state: AgentState = {
            "analysis_id": "test-analysis-123",
            "query": query,
            "research_plan": None,
            "selected_datasets": [],
            "raw_data": {},
            "statistical_results": {},
            "insights": [],
            "citations": [],
            "agent_logs": [],
            "current_agent": AgentName.COORDINATOR,
            "status": "pending",
        }

        # Mock LLM router completing with invalid JSON syntax
        broken_response = LLMResponse(
            content="```json\n{ this is clearly not valid json\n```",
            model="mock-gemini",
            provider="mock",
        )

        with patch("app.agents.coordinator.get_llm_router") as mock_router_getter:
            mock_router = AsyncMock()
            mock_router.complete.return_value = broken_response
            mock_router_getter.return_value = mock_router

            # Execute node
            output_state = await coordinator_node(initial_state)

        # Node must not crash; research_plan must be fully populated
        assert output_state is not None
        plan = output_state.get("research_plan")
        assert plan is not None
        assert isinstance(plan, dict)

        for field in REQUIRED_RESEARCH_PLAN_FIELDS:
            assert field in plan, f"Required field '{field}' missing from fallback plan"
            assert plan[field]

        assert "inflation" in plan["topics"] or "cpi" in plan["topics"]

    def test_markdown_code_fenced_json_parsed_cleanly(self):
        """Markdown code block formatting (```json ... ```) is cleaned and parsed properly."""
        payload = {
            "query_intent": "Examine foreign workforce numbers",
            "target_sectors": ["Services", "Construction"],
            "time_period": "2020-2023",
            "required_metrics": ["pass_holders"],
            "sources": ["singstat", "datagov"],
            "topics": ["employment"],
            "date_range": ["2020", "2023"],
            "sub_tasks": ["Gather pass holders by sector"],
            "planned_datasets": [{"source": "mock", "dataset_id": "M_TEST", "title": "Pass Data"}],
        }
        fenced_json = f"```json\n{json.dumps(payload, indent=2)}\n```"

        plan = _parse_and_validate_plan(fenced_json, "Examine foreign workforce numbers")

        assert plan["query_intent"] == "Examine foreign workforce numbers"
        assert plan["sources"] == ["singstat", "datagov"]
        assert plan["target_sectors"] == ["Services", "Construction"]

    def test_partial_json_missing_fields_supplemented_by_defaults(self):
        """Partial JSON missing optional fields is completed with defaults without raising errors."""
        partial_json = json.dumps(
            {
                "query_intent": "Partial plan query",
                # missing sources, topics, date_range, sub_tasks, etc.
            }
        )

        plan = _parse_and_validate_plan(partial_json, "Examine employment and population growth")

        for field in REQUIRED_RESEARCH_PLAN_FIELDS:
            assert field in plan
            assert plan[field]

        assert plan["query_intent"] == "Partial plan query"
        assert len(plan["sources"]) > 0
        assert len(plan["date_range"]) == 2
