# S18 — Mock Internal Database
**Epic**: E4 Data | **Priority**: P1 | **Assigned**: data-dev  
**Depends on**: S16

## Description
Implement a mock internal data source with realistic Singapore employment and economic statistics pre-loaded as Python dicts. This is the primary data source in test/demo mode.

## Acceptance Criteria
- [x] `backend/app/data_sources/mock_internal.py` — `MockInternalDataSource`
- [x] `source_id = "mock_internal"`, `display_name = "Mock Internal Database"`
- [x] 5 pre-loaded datasets as inline Python data:
  - `employment_by_sector` — annual 2019–2024, 10+ sectors, employment counts
  - `ict_workforce_trends` — annual 2019–2024, ICT headcount + % of workforce
  - `unemployment_rate_quarterly` — quarterly 2019–2024, overall + youth rates
  - `median_gross_wages` — annual 2019–2024, by occupation group
  - `business_registrations` — annual 2019–2024, by industry, new registrations
- [x] `search(keywords)` does case-insensitive keyword matching on dataset title + description
- [x] `fetch(dataset_id)` returns pre-loaded data as `pd.DataFrame` (always succeeds)
- [x] Numbers must be realistic: reference Singapore MOM/SingStat scale (employment in thousands)
- [x] `health_check()` always returns `True`

## Technical Notes
- Singapore total employment ~3.4M people; ICT ~200k; finance ~180k
- Year-over-year realistic: slight COVID dip 2020-2021, recovery 2022-2024
- Include `year`, `sector`, `employment_count`, `yoy_change_pct` columns
