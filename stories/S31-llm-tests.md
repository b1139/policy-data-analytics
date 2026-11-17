# S31 — LLM-Specific Tests & Hallucination Detection
**Epic**: E7 Testing | **Priority**: P1 | **Assigned**: test-engineer  
**Depends on**: S29

## Description
Implement LLM-specific test cases including a `HallucinationDetector` class with three checks. These tests demonstrate quality assurance for AI-generated content — a critical differentiator in the submission.

## Acceptance Criteria
- [ ] `backend/app/services/hallucination_detector.py` — `HallucinationDetector` class:
  - `check_citation_grounding(insights, datasets) → HallucinationCheckResult`:
    - Extracts all source names mentioned in insights text
    - Verifies each mentioned source appears in `datasets` metadata
    - Reports: `{passed: bool, ungrounded_citations: list[str]}`
  - `check_numeric_consistency(insights, stats) → HallucinationCheckResult`:
    - Extracts all numbers/percentages from insights text (regex)
    - For each number: checks if within 15% of any value in stats_result
    - Reports: `{passed: bool, suspicious_numbers: list[str]}`
  - `check_source_attribution(insights) → HallucinationCheckResult`:
    - Verifies all quantitative claims include "according to" / "based on" / year reference
    - Heuristic: sentences with numbers should have attribution
    - Reports: `{passed: bool, unattributed_claims: list[str]}`
- [ ] `tests/llm/test_hallucination_detection.py`:
  - Test `check_citation_grounding` with insight that cites a non-existent source → fails
  - Test `check_numeric_consistency` with number 500% when max stat is 20% → fails
  - Test `check_source_attribution` with bare number claim → fails
  - All 3 checks pass for a well-formed insight + matching stats
- [ ] `tests/llm/test_structured_output.py`:
  - Coordinator LLM output parses to `ResearchPlan` (all required fields present)
  - Invalid JSON from LLM → fallback rule-based plan used (no crash)
- [ ] `tests/llm/test_insight_quality.py`:
  - Insight length between 150–400 words
  - Insight contains at least 1 year reference
  - Insight contains at least 1 percentage or numeric value

## Technical Notes
- Use deterministic `MockLLMProvider` with known outputs for hallucination tests
- Regex for number extraction: `r'\b\d+\.?\d*\s*%'` and `r'\b\d{1,3}(?:,\d{3})*\b'`
- `HallucinationDetector` runs as part of `AnalysisService` and writes report to metadata
