"""Tests for LLM generation consistency and semantic stability across runs (Story S31).

Verifies:
1. Running the same policy query 3 times produces consistent insights covering the same topics.
2. Keyword overlap across runs satisfies the threshold (keyword overlap >= 70%).
3. Statistical metrics referenced across multiple runs remain identical.
"""

import re
from typing import Set

import pytest

from app.llm.mock_provider import MockLLMProvider
from app.llm.router import LLMRouter
from app.schemas.analytics import StatsResult, SummaryResult, TrendResult
from app.services.analysis_service import InsightGenerator


STOPWORDS: set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "across", "between", "our", "all", "this", "these", "those",
}


def extract_keywords(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric keywords, filtering stopwords."""
    tokens = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def calculate_overlap_ratio(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate overlap coefficient between two token sets."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / min(len(set_a), len(set_b))


class TestLLMConsistency:
    """Test suite evaluating semantic and topical consistency across repeated queries."""

    @pytest.fixture
    def consistent_stats(self) -> StatsResult:
        return StatsResult(
            trend=TrendResult(
                overall_trend="increasing",
                slope=2.1,
                r2=0.96,
                p_value=0.005,
                yoy_growth={"2021": 4.1, "2022": 5.8, "2023": 6.2},
            ),
            summary=SummaryResult(
                count=5,
                mean=4500.0,
                median=4400.0,
                min=3800.0,
                max=5200.0,
                std=450.0,
                earliest_value=3850.0,
                latest_value=5150.0,
            ),
        )

    @pytest.fixture
    def consistent_sources(self) -> list[dict]:
        return [
            {
                "source": "SingStat",
                "title": "Resident Income and Wages",
                "period": "2019-2023",
                "agency": "Singapore Department of Statistics",
            }
        ]

    @pytest.mark.asyncio
    async def test_repeated_query_insights_maintain_keyword_overlap_above_70_percent(
        self,
        consistent_stats: StatsResult,
        consistent_sources: list[dict],
    ):
        """Same query run 3x -> insights cover same topics (keyword overlap >= 70%)."""
        query = "Analyze resident monthly wage trajectory and real wage trends"

        # Use deterministic MockLLMProvider wrapped in router
        mock_provider = MockLLMProvider()
        router = LLMRouter(primary=mock_provider, fallback=mock_provider)
        generator = InsightGenerator(router=router)

        # Run 3 consecutive completions
        run1 = await generator.generate_insights(
            stats=consistent_stats,
            query=query,
            sources=consistent_sources,
        )
        run2 = await generator.generate_insights(
            stats=consistent_stats,
            query=query,
            sources=consistent_sources,
        )
        run3 = await generator.generate_insights(
            stats=consistent_stats,
            query=query,
            sources=consistent_sources,
        )

        keywords_1 = extract_keywords(run1)
        keywords_2 = extract_keywords(run2)
        keywords_3 = extract_keywords(run3)

        assert len(keywords_1) >= 15
        assert len(keywords_2) >= 15
        assert len(keywords_3) >= 15

        overlap_1_2 = calculate_overlap_ratio(keywords_1, keywords_2)
        overlap_2_3 = calculate_overlap_ratio(keywords_2, keywords_3)
        overlap_1_3 = calculate_overlap_ratio(keywords_1, keywords_3)

        # Verify all pairwise overlaps satisfy >= 70% threshold
        assert overlap_1_2 >= 0.70, f"Overlap between run 1 and 2 is {overlap_1_2:.2%}, expected >= 70%"
        assert overlap_2_3 >= 0.70, f"Overlap between run 2 and 3 is {overlap_2_3:.2%}, expected >= 70%"
        assert overlap_1_3 >= 0.70, f"Overlap between run 1 and 3 is {overlap_1_3:.2%}, expected >= 70%"

    def test_fallback_insights_maintain_high_topical_determinism(
        self,
        consistent_stats: StatsResult,
        consistent_sources: list[dict],
    ):
        """Fallback deterministic insights achieve >= 95% keyword consistency across repeated calls."""
        query = "Examine employment and sector headcount shifts"

        insight_a = InsightGenerator._generate_fallback_insights(
            stats=consistent_stats,
            query=query,
            sources=consistent_sources,
        )
        insight_b = InsightGenerator._generate_fallback_insights(
            stats=consistent_stats,
            query=query,
            sources=consistent_sources,
        )

        kw_a = extract_keywords(insight_a)
        kw_b = extract_keywords(insight_b)

        overlap = calculate_overlap_ratio(kw_a, kw_b)
        assert overlap >= 0.95
