"""Unit and integration tests for LLM hallucination detection (Story S31).

Verifies:
1. check_citation_grounding flags non-existent and ungrounded sources.
2. check_numeric_consistency flags numbers diverging > 15% from computed statistics (e.g. 500% vs 20%).
3. check_source_attribution flags quantitative claims lacking attribution phrases or year references.
4. All 3 checks pass cleanly for a well-formed, grounded insight narrative.
5. Composite verification report generation via run_all_checks and AnalysisService.
"""

import pytest

from app.services.analysis_service import AnalysisService
from app.services.hallucination_detector import (
    HallucinationCheckResult,
    HallucinationDetector,
)


class TestHallucinationDetection:
    """Test suite for HallucinationDetector checks."""

    @pytest.fixture
    def detector(self) -> HallucinationDetector:
        return HallucinationDetector()

    @pytest.fixture
    def valid_datasets(self) -> list[dict]:
        return [
            {
                "source": "singstat",
                "dataset_id": "M810361",
                "title": "Resident Employment by Industry",
                "agency": "Singapore Department of Statistics",
            },
            {
                "source": "mom",
                "dataset_id": "MOM_WAGE_2023",
                "title": "Occupational Wage Table",
                "agency": "Ministry of Manpower",
            },
        ]

    @pytest.fixture
    def valid_stats(self) -> dict:
        return {
            "summary": {
                "mean": 15.2,
                "median": 14.8,
                "min": 10.0,
                "max": 20.0,
                "earliest_value": 10.5,
                "latest_value": 19.8,
            },
            "trend": {
                "overall_trend": "increasing",
                "slope": 1.5,
                "yoy_growth": {
                    "2020": 4.5,
                    "2021": 6.2,
                    "2022": 7.8,
                    "2023": 5.1,
                },
            },
            "years": [2019, 2020, 2021, 2022, 2023],
            "total_count": 5000,
        }

    # 1. Citation Grounding Tests

    def test_citation_grounding_with_ungrounded_source_fails(
        self,
        detector: HallucinationDetector,
        valid_datasets: list[dict],
    ):
        """Test check_citation_grounding with insight that cites a non-existent source -> fails."""
        # The insight cites the World Bank and Eurostat, neither of which exists in valid_datasets
        insight_with_fake_source = (
            "According to the World Bank, Singapore's economic expansion slowed in 2023. "
            "Additionally, Eurostat reports that manufacturing exports decreased."
        )

        result = detector.check_citation_grounding(insight_with_fake_source, valid_datasets)

        assert isinstance(result, HallucinationCheckResult)
        assert result.passed is False
        assert result["passed"] is False
        assert len(result.ungrounded_citations) > 0
        assert any("World Bank" in s for s in result.ungrounded_citations)

    def test_citation_grounding_with_grounded_sources_passes(
        self,
        detector: HallucinationDetector,
        valid_datasets: list[dict],
    ):
        """Test check_citation_grounding passes when all cited sources exist in metadata."""
        insight = (
            "Based on official statistics from SingStat, resident employment improved steadily. "
            "According to the Ministry of Manpower, wage progression remained resilient."
        )

        result = detector.check_citation_grounding(insight, valid_datasets)

        assert result.passed is True
        assert len(result.ungrounded_citations) == 0

    def test_citation_grounding_with_empty_insight(
        self,
        detector: HallucinationDetector,
        valid_datasets: list[dict],
    ):
        """Empty insight gracefully passes grounding checks."""
        result = detector.check_citation_grounding("", valid_datasets)
        assert result.passed is True
        assert len(result.ungrounded_citations) == 0

    # 2. Numeric Consistency Tests

    def test_numeric_consistency_with_extreme_number_fails(
        self,
        detector: HallucinationDetector,
        valid_stats: dict,
    ):
        """Test check_numeric_consistency with number 500% when max stat is 20% -> fails."""
        # Stats max is 20.0, but the insight claims 500%
        insight_with_extreme_stat = (
            "According to SingStat in 2023, resident employment surged by 500% across all sectors."
        )

        result = detector.check_numeric_consistency(insight_with_extreme_stat, valid_stats)

        assert isinstance(result, HallucinationCheckResult)
        assert result.passed is False
        assert result["passed"] is False
        assert len(result.suspicious_numbers) > 0
        assert any("500%" in num for num in result.suspicious_numbers)

    def test_numeric_consistency_within_15_percent_tolerance_passes(
        self,
        detector: HallucinationDetector,
        valid_stats: dict,
    ):
        """Numbers within 15% of actual statistics pass consistency checks."""
        # Max stat is 20.0; 19.5% is within 2.5% (< 15% tolerance)
        # Median is 14.8; 15.0 is within 1.4%
        insight = (
            "According to official figures in 2023, peak utilization reached 19.5%, "
            "while median compensation hovered around 15.0 based on documented trends."
        )

        result = detector.check_numeric_consistency(insight, valid_stats)

        assert result.passed is True
        assert len(result.suspicious_numbers) == 0

    def test_numeric_consistency_recognizes_calendar_years(
        self,
        detector: HallucinationDetector,
        valid_stats: dict,
    ):
        """4-digit calendar years matching dataset periods are recognized as temporal anchors."""
        insight = (
            "From 2019 to 2023, the baseline index rose according to official records, "
            "registering a minimum level of 10.0 and maximum of 20.0."
        )

        result = detector.check_numeric_consistency(insight, valid_stats)

        assert result.passed is True
        assert len(result.suspicious_numbers) == 0

    # 3. Source Attribution Tests

    def test_source_attribution_with_bare_number_claim_fails(
        self,
        detector: HallucinationDetector,
    ):
        """Test check_source_attribution with bare number claim -> fails."""
        # Sentence contains a quantitative number (12.5% and 8,000) but no attribution phrase or year
        bare_claim_insight = (
            "Unemployment surged dramatically to 12.5% with over 8,000 workers displaced."
        )

        result = detector.check_source_attribution(bare_claim_insight)

        assert isinstance(result, HallucinationCheckResult)
        assert result.passed is False
        assert result["passed"] is False
        assert len(result.unattributed_claims) > 0
        assert any("12.5%" in claim for claim in result.unattributed_claims)

    def test_source_attribution_with_attribution_phrases_passes(
        self,
        detector: HallucinationDetector,
    ):
        """Sentences containing 'according to', 'based on', or similar phrases pass."""
        insight = (
            "According to official survey data, resident employment expanded by 3.5%. "
            "Based on ministry records, average wages grew steadily."
        )

        result = detector.check_source_attribution(insight)

        assert result.passed is True
        assert len(result.unattributed_claims) == 0

    def test_source_attribution_with_year_reference_passes(
        self,
        detector: HallucinationDetector,
    ):
        """Sentences with 4-digit year reference pass attribution requirement."""
        insight = "In 2023, resident employment expanded by 3.5% across technical domains."

        result = detector.check_source_attribution(insight)

        assert result.passed is True
        assert len(result.unattributed_claims) == 0

    # 4. Composite All-Checks Passes Test

    def test_all_three_checks_pass_for_well_formed_insight(
        self,
        detector: HallucinationDetector,
        valid_datasets: list[dict],
        valid_stats: dict,
    ):
        """All 3 checks pass for a well-formed insight + matching stats."""
        well_formed_insight = (
            "According to official statistics from SingStat, resident employment trended positively "
            "between 2019 and 2023, recording an average mean of 15.2 and peak of 20.0. "
            "Based on Ministry of Manpower records in 2023, year-over-year expansion registered 5.1%, "
            "demonstrating sustained labor market resilience across core sectors."
        )

        # Individual check validations
        grounding_result = detector.check_citation_grounding(well_formed_insight, valid_datasets)
        numeric_result = detector.check_numeric_consistency(well_formed_insight, valid_stats)
        attribution_result = detector.check_source_attribution(well_formed_insight)

        assert grounding_result.passed is True
        assert len(grounding_result.ungrounded_citations) == 0

        assert numeric_result.passed is True
        assert len(numeric_result.suspicious_numbers) == 0

        assert attribution_result.passed is True
        assert len(attribution_result.unattributed_claims) == 0

        # Composite report validation
        full_report = detector.run_all_checks(
            insights=well_formed_insight,
            datasets=valid_datasets,
            stats=valid_stats,
        )

        assert full_report["passed"] is True
        assert full_report["citation_grounding"]["passed"] is True
        assert full_report["numeric_consistency"]["passed"] is True
        assert full_report["source_attribution"]["passed"] is True
        assert len(full_report["ungrounded_citations"]) == 0
        assert len(full_report["suspicious_numbers"]) == 0
        assert len(full_report["unattributed_claims"]) == 0

    def test_analysis_service_verify_hallucinations_facade(
        self,
        valid_datasets: list[dict],
        valid_stats: dict,
    ):
        """AnalysisService.verify_hallucinations provides seamless static verification facade."""
        insight = (
            "According to SingStat statistics between 2019 and 2023, mean performance stood at 15.2. "
            "Based on Ministry of Manpower records, peak recorded figures reached 20.0."
        )

        report = AnalysisService.verify_hallucinations(
            insights=insight,
            datasets=valid_datasets,
            stats=valid_stats,
        )

        assert report["passed"] is True
        assert "citation_grounding" in report
        assert "numeric_consistency" in report
        assert "source_attribution" in report
