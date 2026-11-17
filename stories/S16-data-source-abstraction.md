# S16 — Data Source Abstraction & Registry
**Epic**: E4 Data | **Priority**: P0 | **Assigned**: data-dev  
**Depends on**: S04

## Description
Create the abstract data source interface and registry pattern. All data connectors implement the same interface; the registry provides discovery by source ID. The extraction agent uses this registry without knowing which concrete source it's calling.

## Acceptance Criteria
- [x] `backend/app/data_sources/base.py` — `AbstractDataSource` ABC matching LLD.md §6
- [x] `search(keywords, **filters) → list[dict]` with result schema: `[{id, title, description, url, format}]`
- [x] `fetch(dataset_id: str) → pd.DataFrame` returns normalized DataFrame (lowercase cols, UTC dates)
- [x] `health_check() → bool` with 5-second timeout
- [x] `backend/app/data_sources/registry.py` — `DataSourceRegistry` singleton
  - `register(source: AbstractDataSource)` registers by `source.source_id`
  - `get(source_id: str) → AbstractDataSource` raises `KeyError` if not found
  - `list_all() → list[str]` returns all registered source IDs
- [x] `backend/app/data_sources/__init__.py` auto-registers all concrete sources on import
- [x] `fetch()` always returns a DataFrame (empty `pd.DataFrame()` on error, never raises)
- [x] `source_id` and `display_name` class attributes required on all implementations

## Technical Notes
- Registry initialized at app startup via lifespan event
- `source_id` values: `"singstat"`, `"datagov"`, `"mock_internal"`
