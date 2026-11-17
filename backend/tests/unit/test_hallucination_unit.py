"""Unit tests for HallucinationDetector covering grounding, numeric consistency, and attribution."""

from types import SimpleNamespace

import pytest

from app.services.hallucination_detector import HallucinationDetector


@pytest.fixture
def detector() -> HallucinationDetector:
    return HallucinationDetector()


def test_check_citation_grounding_empty_and_object_datasets(detector: HallucinationDetector):
    """Verify check_citation_grounding with empty string and object datasets."""
    # Empty string
    empty_res = detector.check_citation_grounding("", [])
    assert empty_res.passed is True
    assert empty_res.ungrounded_citations == []

    # Datasets as objects (not dicts)
    ds_obj = SimpleNamespace(
        source="singstat",
        title="Resident Labor Force",
        agency="Ministry of Manpower",
        id="M81001",
    )
    # Mentioning valid source
    valid_res = detector.check_citation_grounding(
        "According to SingStat and the Ministry of Manpower, resident workforce grew.",
        datasets=[ds_obj],
    )
    assert valid_res.passed is True
    assert valid_res.ungrounded_citations == []

    # Mentioning external body like World Bank
    invalid_res = detector.check_citation_grounding(
        "According to the World Bank and OECD, Singapore GDP doubled.",
        datasets=[ds_obj],
    )
    assert invalid_res.passed is False
    assert any("World Bank" in cite for cite in invalid_res.ungrounded_citations)


def test_check_numeric_consistency_branches(detector: HallucinationDetector):
    """Verify numeric consistency check with percentages, decimals, calendar years, and ordinals."""
    # Empty string
    empty_res = detector.check_numeric_consistency("", {})
    assert empty_res.passed is True

    stats = {
        "mean": 50.0,
        "growth_rate": 0.12,  # 12%
        "years": [2020, 2021, 2022],
        "total": 1250.0,
    }

    # Consistent text
    good_text = (
        "1. In 2021, the growth was 12.0% with a mean value of 50.0 and total reaching 1,250."
    )
    res_good = detector.check_numeric_consistency(good_text, stats)
    assert res_good.passed is True
    assert res_good.suspicious_numbers == []

    # Inconsistent percentage and large number
    bad_text = "The employment surged by 85% with an average of 999.0."
    res_bad = detector.check_numeric_consistency(bad_text, stats, tolerance=0.10)
    assert res_bad.passed is False
    assert "85%" in res_bad.suspicious_numbers
    assert "999.0" in res_bad.suspicious_numbers


def test_check_source_attribution_branches(detector: HallucinationDetector):
    """Verify source attribution checks on sentences with numbers."""
    # Empty text
    empty_res = detector.check_source_attribution("")
    assert empty_res.passed is True

    # Attributed sentences
    valid_text = (
        "Based on official statistics, employment rose by 5.2% in 2022. "
        "According to SingStat data, resident workforce reached 2.4 million."
    )
    res_valid = detector.check_source_attribution(valid_text)
    assert res_valid.passed is True
    assert res_valid.unattributed_claims == []

    # Unattributed quantitative claim
    invalid_text = "Total revenue grew by 15.5% without any context or year."
    res_invalid = detector.check_source_attribution(invalid_text)
    assert res_invalid.passed is False
    assert len(res_invalid.unattributed_claims) > 0


def test_detector_helpers(detector: HallucinationDetector):
    """Verify helper extraction functions."""
    stats = {
        "mean": 45.2,
        "years": [2021, 2022, 2023],
        "nested": {"count": 100},
    }
    numbers = detector._extract_numbers_from_stats(stats)
    assert 45.2 in numbers
    assert 100.0 in numbers

    years = detector._extract_calendar_years(stats)
    assert 2021 in years
    assert 2023 in years
