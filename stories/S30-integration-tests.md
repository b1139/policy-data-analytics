# S30 — Integration Tests — Multi-Agent Workflows
**Epic**: E7 Testing | **Priority**: P0 | **Assigned**: test-engineer  
**Depends on**: S29

## Description
Write integration tests that run the full LangGraph multi-agent pipeline end-to-end using mock LLM and mock data sources. Verify agent coordination, database persistence, and WebSocket message delivery.

## Acceptance Criteria
- [ ] `tests/integration/test_full_pipeline.py`:
  - Full graph run: `run_analysis(analysis_id, query)` with mock providers
  - Assert: `Analysis.status == "DONE"` after completion
  - Assert: `AgentLog` rows exist for all 3 agents (coordinator, extraction, analytics)
  - Assert: `Analysis.result` contains non-empty `insights` and `charts`
  - Assert: at least 1 `Dataset` row created and linked to analysis
- [ ] `tests/integration/test_agent_sequence.py`:
  - Verify coordinator runs first (lowest sequence_no agent_logs)
  - Verify extraction runs second
  - Verify analytics runs last
  - Verify `research_plan` populated after coordinator step
- [ ] `tests/integration/test_fallback_behavior.py`:
  - Configure `LLMRouter` with mock primary that always fails
  - Verify fallback provider called
  - Verify analysis still completes with `DONE` status
  - Configure both providers to fail → analysis status is `FAILED`
- [ ] `tests/integration/test_websocket_messages.py`:
  - Connect to WS endpoint, run analysis, collect messages
  - Assert: at least 1 `AGENT_STEP` message per agent
  - Assert: final message is `ANALYSIS_DONE`
  - Assert: messages arrive in `sequence_no` order

## Technical Notes
- Integration tests use real PostgreSQL (via test docker compose) or SQLite in-memory
- Use `pytest-asyncio` with `asyncio_mode="auto"` in `pyproject.toml`
- WS test: use `httpx` websocket client + asyncio event collection
