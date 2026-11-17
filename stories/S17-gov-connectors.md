# S17 — SingStat & Data.gov.sg Connectors
**Epic**: E4 Data | **Priority**: P0 | **Assigned**: data-dev  
**Depends on**: S16

## Description
Implement real HTTP connectors to SingStat Table Builder API and Data.gov.sg CKAN API. Both must degrade gracefully to mock data when API keys are absent or APIs are unavailable.

## Acceptance Criteria
- [x] `backend/app/data_sources/singstat.py` — `SingStatDataSource`
  - `source_id = "singstat"`, `display_name = "SingStat Table Builder"`
  - `search()`: hits `https://tablebuilder.singstat.gov.sg/api/table/search?keyword={kw}`
  - `fetch()`: downloads time series data from `https://tablebuilder.singstat.gov.sg/api/table/tabledata/{id}`
  - Both methods: fall back to `MockInternalDataSource` if `USE_MOCK_DATA_SOURCES=true` or HTTP error
  - Timeout: 30 seconds on all requests
- [x] `backend/app/data_sources/datagov.py` — `DataGovDataSource`
  - `source_id = "datagov"`, `display_name = "Data.gov.sg"`
  - `search()`: hits `https://data.gov.sg/api/action/package_search?q={kw}`
  - `fetch()`: downloads resource from `https://data.gov.sg/api/action/datastore_search?resource_id={id}`
  - Falls back gracefully on any failure
- [x] Both connectors: normalize DataFrame columns (lowercase, underscores, strip whitespace)
- [x] Both connectors: add `_source` and `_fetched_at` columns to returned DataFrame
- [x] `health_check()`: simple GET to API root; timeout 5s; returns bool

## Technical Notes
- Use `httpx.AsyncClient(timeout=30)` for all requests
- SingStat requires no auth for public datasets
- Data.gov.sg: use `DATAGOV_API_TOKEN` as Bearer token if set, else public access
- Handle both CSV and JSON response formats
