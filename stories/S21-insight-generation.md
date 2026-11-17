# S21 — LLM-Powered Insight Generation
**Epic**: E5 Analytics | **Priority**: P0 | **Assigned**: analytics-dev  
**Depends on**: S20, S09

## Description
Build the `InsightGenerator` that uses an LLM to convert statistical outputs into natural language policy insights. Insights must be grounded in the actual data and include proper citations.

## Acceptance Criteria
- [x] `backend/app/services/analysis_service.py` — `InsightGenerator` class
- [x] `generate_insights(stats: StatsResult, query: str, sources: list[dict]) → str`
- [x] LLM system prompt instructs:
  - Act as Singapore policy analyst
  - Base all claims on provided statistics (no hallucination)
  - Cite dataset names and years for every quantitative claim
  - Identify policy implications
  - Use plain English (not jargon-heavy)
- [x] LLM user prompt includes: query, stats summary dict, source titles
- [x] Template-based fallback if LLM fails:
  - `"Based on data from {sources}, {trend_description} was observed in {topic} between {date_range}."`
- [x] Insights string: 150–400 words, 3–5 paragraphs
- [x] `generate_insight` LangChain tool wrapper in `llm_tools.py` calls this service

## Technical Notes
- Use `temperature=0.5` for balanced creativity and accuracy
- Include in prompt: "Only reference statistics from the provided stats_dict. Do not invent numbers."
- If insight contains a number NOT in stats_dict → test suite will flag this (S31)
