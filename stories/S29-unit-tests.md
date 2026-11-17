# S29 — Unit Tests — Backend & Agents
**Epic**: E7 Testing | **Priority**: P0 | **Assigned**: test-engineer  
**Depends on**: S15, S19

## Description
Write comprehensive unit tests for all backend modules and agent tools. All external calls (LLM, data sources, HTTP) must be mocked. Target ≥80% coverage on `app/agents/`, `app/api/`, `app/services/`, `app/llm/`.

## Acceptance Criteria
- [x] `backend/tests/conftest.py` with fixtures:
  - `async_db_session` — in-memory SQLite async
  - `mock_llm_provider` — `MockLLMProvider` instance
  - `mock_data_registry` — registry with `MockInternalDataSource` only
  - `test_client` — `AsyncClient(app=app)` from httpx
- [x] `tests/unit/test_llm_router.py`:
  - Primary succeeds → fallback never called
  - Primary fails once → retried → succeeds
  - Primary fails 3× → fallback called
  - Both fail → `AllProvidersFailedError` raised
- [x] `tests/unit/test_data_sources.py`:
  - `MockInternalDataSource.search()` returns non-empty list
  - `MockInternalDataSource.fetch()` returns DataFrame with correct columns
  - `SingStatDataSource` with `USE_MOCK_DATA_SOURCES=true` → returns mock data
- [x] `tests/unit/test_data_quality.py`:
  - Empty DataFrame → `passed=False`
  - DataFrame with 50% nulls → warning generated
  - DataFrame with outlier (1000x median) → outlier warning
- [x] `tests/unit/test_statistics.py`:
  - `compute_trend` with monotonically increasing data → `overall_trend="increasing"`
  - `compute_summary_stats` correct mean/median
  - `compute_trend` with <3 rows → error result, no crash
- [x] `tests/unit/test_api_endpoints.py`:
  - `POST /api/v1/analysis/start` returns 201 + `{analysis_id, ws_url}`
  - `GET /api/v1/analysis/{id}` returns 404 for unknown ID
  - `GET /api/v1/health` returns 200 with db/redis status
- [x] Coverage report: `pytest --cov=app --cov-fail-under=80`

## Technical Notes
- Use `@pytest.mark.asyncio` on all async tests
- Mock httpx using `respx` library for HTTP mocks
- Mock LLM: `MockLLMProvider` returns pre-configured canned responses
