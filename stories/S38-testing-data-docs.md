# S38 — TESTING.md & DATA_SOURCES.md
**Epic**: E9 Docs | **Priority**: P1 | **Assigned**: doc-writer  
**Depends on**: S31, S19

## Description
Write the final two submission documentation files: TESTING.md covering the full test strategy and hallucination detection approach, and DATA_SOURCES.md documenting all data sources used.

## Acceptance Criteria
**TESTING.md**:
- [ ] Testing philosophy and approach
- [ ] Test categories table: unit / integration / LLM-specific / E2E / perf, with count + file location
- [ ] How to run each category (exact commands)
- [ ] **Hallucination Detection section** (prominent):
  - Three detection methods explained: citation grounding, numeric consistency, source attribution
  - How false positives are handled
  - Limitations acknowledged
- [ ] Coverage report: actual numbers from `pytest --cov` output
- [ ] Known test limitations and future improvements

**DATA_SOURCES.md**:
- [ ] SingStat Table Builder API: base URL, endpoint docs, authentication, rate limits, data formats
- [ ] Data.gov.sg CKAN API: base URL, key endpoints, authentication, example datasets used
- [ ] Mock data approach: schema, datasets included, realistic data assumptions
- [ ] Data quality issues encountered during development
- [ ] How to add a new data source (3-step guide: implement interface, register, done)
- [ ] Data refresh strategy: TTL-based caching via `datasets.expires_at`

## Technical Notes
- Include real coverage percentages (not estimates)
- DATA_SOURCES.md should include example API responses (truncated JSON)
