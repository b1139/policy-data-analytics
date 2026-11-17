"""Unit tests for LLM-powered insight generation and policy narrative synthesis (Story S21)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.tools.analysis_tools import generate_insight
from app.llm.base import LLMResponse
from app.llm.exceptions import AllProvidersFailedError
from app.schemas.analytics import (
    CorrelationResult,
    SectorShareResult,
    StatsResult,
    SummaryResult,
    TrendResult,
)
from app.services.analysis_service import InsightGenerator


@pytest.fixture
def sample_sources() -> list[dict[str, str]]:
    """Sample official Singapore statistical data sources."""
    return [
        {
            "title": "SingStat Labour Force Statistics",
            "period": "2019-2023",
            "publisher": "Ministry of Manpower",
            "dataset_id": "MOM-LFS-01",
        },
        {
            "title": "Economic Survey of Singapore",
            "period": "2019-2023",
            "publisher": "Ministry of Trade and Industry",
            "dataset_id": "MTI-ESS-02",
        },
    ]


@pytest.fixture
def sample_stats() -> StatsResult:
    """Sample structured statistical calculations."""
    return StatsResult(
        trend=TrendResult(
            slope=1.45,
            intercept=78.2,
            r2=0.88,
            p_value=0.012,
            overall_trend="increasing",
            yoy_growth={"2020": 2.1, "2021": 3.4, "2022": 4.1, "2023": 2.8},
        ),
        summary=SummaryResult(
            mean=82.5,
            median=82.1,
            std=3.14,
            min=78.4,
            max=86.9,
            count=5,
            earliest_value=78.4,
            latest_value=86.9,
        ),
        sector_shares=SectorShareResult(
            year="2023",
            shares={"Technology": 38.5, "Finance": 31.2, "Manufacturing": 20.3},
        ),
        correlations=[
            CorrelationResult(
                pearson_r=0.82,
                spearman_r=0.79,
                p_value=0.008,
                interpretation="Strong positive correlation (r=0.82, statistically significant (p < 0.05)).",
            )
        ],
        metadata={"indicator": "Resident Employment Rate (%)"},
    )


class TestInsightGeneratorPrompting:
    """Test grounding rules, system prompt specifications, and prompt formatting."""

    def test_system_prompt_grounding_rules(self) -> None:
        """Verify system prompt contains all required grounding and policy analyst directives."""
        system_prompt = InsightGenerator.SYSTEM_PROMPT.lower()
        assert "singapore policy" in system_prompt
        assert "invent numbers" in system_prompt
        assert "plain english" in system_prompt
        assert "bullet" in system_prompt

    def test_grounding_instruction(self) -> None:
        """Verify strict grounding instruction forbids inventing numbers."""
        assert (
            "Only use numbers from stats" in InsightGenerator.GROUNDING_INSTRUCTION
            or "Do not invent numbers" in InsightGenerator.GROUNDING_INSTRUCTION
        )

    def test_source_formatting(self, sample_sources: list[dict[str, str]]) -> None:
        """Verify sources formatting includes titles, periods, and publishers."""
        formatted = InsightGenerator._format_sources_for_prompt(sample_sources)
        assert "SingStat Labour Force Statistics (2019-2023)" in formatted
        assert "Publisher: Ministry of Manpower" in formatted
        assert "Economic Survey of Singapore" in formatted


class TestInsightGeneratorLLM:
    """Test LLM generation with mocked router."""

    @pytest.mark.asyncio
    async def test_llm_generation_success(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify generator calls router with temperature=0.5 and returns LLM narrative."""
        mock_narrative = (
            "Based on official statistics from SingStat Labour Force Statistics (2019-2023), "
            "resident employment exhibited an increasing trend with an annual regression slope "
            "of +1.45 (R² = 0.88, p = 0.012). Across the 5 recorded observations, the average rate "
            "was 82.5%.\n\n"
            "Sectoral allocation in 2023 indicates Technology accounted for 38.5% and Finance for 31.2%. "
            "A strong positive correlation (r = 0.82, p = 0.008) highlights synchronized expansion.\n\n"
            "From a public policy perspective, manpower authorities should continue targeted workforce "
            "support to sustain high-value tech and financial sector productivity."
        )

        mock_router = MagicMock()
        mock_router.complete = AsyncMock(
            return_value=LLMResponse(
                content=mock_narrative,
                model="mock-gemini",
                provider="gemini",
            )
        )

        generator = InsightGenerator(router=mock_router)
        result = await generator.generate_insights(
            stats=sample_stats,
            query="Analyze Singapore employment trends from 2019 to 2023",
            sources=sample_sources,
        )

        assert result == mock_narrative
        mock_router.complete.assert_awaited_once()
        call_kwargs = mock_router.complete.await_args.kwargs
        assert call_kwargs["temperature"] in (0.3, 0.5)
        assert call_kwargs["max_tokens"] in (450, 800)

        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == InsightGenerator.SYSTEM_PROMPT

        user_content = messages[1]["content"]
        assert "Analyze Singapore employment trends from 2019 to 2023" in user_content
        assert "SingStat Labour Force Statistics" in user_content
        assert (
            "Only reference statistics from the provided stats_dict. Do not invent numbers."
            in user_content
            or "Markdown, exactly:" in user_content
        )
        assert "82.5" in user_content

    @pytest.mark.asyncio
    async def test_llm_generation_with_dict_stats(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify generator accepts dict stats directly."""
        mock_router = MagicMock()
        mock_router.complete = AsyncMock(
            return_value=LLMResponse(
                content="Grounded insight narrative.",
                model="mock-gemini",
                provider="gemini",
            )
        )

        generator = InsightGenerator(router=mock_router)
        res = await generator.generate_insights(
            stats=sample_stats.model_dump(),
            query="Employment rate inquiry",
            sources=sample_sources,
        )
        assert res == "Grounded insight narrative."


class TestInsightGeneratorFallback:
    """Test deterministic template fallback when LLM fails or produces empty output."""

    @pytest.mark.asyncio
    async def test_fallback_on_all_providers_failed(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify template fallback triggers when LLM router raises AllProvidersFailedError."""
        mock_router = MagicMock()
        mock_router.complete = AsyncMock(
            side_effect=AllProvidersFailedError(
                "Both primary and fallback failed",
                provider="router",
            )
        )

        generator = InsightGenerator(router=mock_router)
        query = "What are the recent trends in Singapore employment?"
        result = await generator.generate_insights(
            stats=sample_stats,
            query=query,
            sources=sample_sources,
        )

        assert result is not None
        assert result.startswith("**Answer:**")
        assert "official statistics from SingStat Labour Force Statistics" in result
        assert "**Key Findings**" in result
        assert "**Policy Implications**" in result
        assert "increasing" in result.lower() or "rose" in result
        assert "82.50" in result
        assert "Technology (38.5%)" in result

        # Bullet-point format
        bullets = [ln for ln in result.splitlines() if ln.startswith("- ")]
        assert len(bullets) >= 4

    @pytest.mark.asyncio
    async def test_fallback_on_empty_llm_response(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify fallback triggers when LLM response content is empty or whitespace."""
        mock_router = MagicMock()
        mock_router.complete = AsyncMock(
            return_value=LLMResponse(
                content="   ",
                model="mock-gemini",
                provider="gemini",
            )
        )

        generator = InsightGenerator(router=mock_router)
        result = await generator.generate_insights(
            stats=sample_stats,
            query="Singapore employment indicators",
            sources=sample_sources,
        )

        assert result.startswith("**Answer:**")
        assert "- " in result

    @pytest.mark.asyncio
    async def test_fallback_with_minimal_stats(self) -> None:
        """Verify fallback handles minimal or empty stats gracefully."""
        minimal_stats = StatsResult()
        generator = InsightGenerator()
        fallback = generator._generate_fallback_insights(
            stats=minimal_stats,
            query="General policy indicator analysis",
            sources=[],
        )

        assert "official statistics from official government statistics" in fallback
        assert "**Policy Implications**" in fallback


class TestInsightGeneratorInvocationStyles:
    """Test calling InsightGenerator as classmethod vs instance."""

    @pytest.mark.asyncio
    async def test_class_level_generate_insights(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify InsightGenerator.generate_insights can be invoked directly as a classmethod."""
        result = await InsightGenerator.generate_insights(
            stats=sample_stats,
            query="Evaluate labor statistics",
            sources=sample_sources,
        )
        assert isinstance(result, str)
        assert len(result.split()) >= 30


class TestLangChainAnalysisTools:
    """Test generate_insight LangChain tool wrapper."""

    @pytest.mark.asyncio
    async def test_tool_with_dict(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify generate_insight tool execution via ainvoke with dictionary parameters."""
        res = await generate_insight.ainvoke(
            {
                "query": "Singapore employment statistics",
                "stats": sample_stats.model_dump(),
                "sources": sample_sources,
            }
        )
        assert isinstance(res, str)
        assert "official statistics" in res.lower()
        assert len(res.split()) >= 120

    @pytest.mark.asyncio
    async def test_tool_with_json_string(
        self,
        sample_stats: StatsResult,
        sample_sources: list[dict[str, str]],
    ) -> None:
        """Verify generate_insight tool accepts serialized JSON strings."""
        stats_json = json.dumps(sample_stats.model_dump())
        sources_json = json.dumps(sample_sources)

        res = await generate_insight.ainvoke(
            {
                "query": "Singapore employment statistics",
                "stats": stats_json,
                "sources": sources_json,
            }
        )
        assert isinstance(res, str)
        assert len(res.split()) >= 120

    @pytest.mark.asyncio
    async def test_tool_error_resilience(self) -> None:
        """Verify generate_insight tool falls back safely if invalid JSON is passed."""
        res = await generate_insight.ainvoke(
            {
                "query": "Invalid JSON test query",
                "stats": "{malformed-json:",
                "sources": "[]",
            }
        )
        assert isinstance(res, str)
        assert "official statistics" in res.lower()
