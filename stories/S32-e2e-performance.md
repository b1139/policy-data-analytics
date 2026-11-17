# S32 — E2E & Performance Tests
**Epic**: E7 Testing | **Priority**: P2 | **Assigned**: test-engineer  
**Depends on**: S30

## Description
Write end-to-end tests covering the complete user journey and performance tests for concurrent analysis requests. Generate final coverage reports for both backend and frontend.

## Acceptance Criteria
- [ ] `tests/perf/test_concurrent_analyses.py`:
  - 10 concurrent `run_analysis()` calls (mock LLM + mock data)
  - All 10 complete with `DONE` status
  - No DB deadlocks or connection pool exhaustion
  - P95 completion time < 10 seconds (mock mode)
- [ ] `tests/perf/test_websocket_load.py`:
  - 10 concurrent WebSocket connections to same analysis
  - All connections receive all messages
  - No messages dropped
- [ ] Frontend unit tests:
  - `QueryInput.test.tsx` — renders, submit disabled when empty, fires callback on submit
  - `AgentMonitor.test.tsx` — renders steps list, auto-scrolls
  - `HistoryList.test.tsx` — renders empty state, renders analysis cards
- [ ] Coverage report generated:
  - Backend: `pytest --cov=app --cov-report=html:coverage_html tests/`
  - Frontend: `jest --coverage --coverageReporters=html`
- [ ] `TESTING.md` coverage numbers written from actual reports (not estimates)

## Technical Notes
- Use `asyncio.gather()` for concurrent test execution
- pytest-asyncio event loop scoped to session for perf tests
- Frontend tests: mock `fetch` using `jest.spyOn(global, 'fetch')`
