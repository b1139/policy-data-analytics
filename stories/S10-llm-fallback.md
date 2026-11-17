# S10 — LLM Fallback & Health Check
**Epic**: E2 LLM Integration | **Priority**: P1 | **Assigned**: llm-integration-dev  
**Depends on**: S09

## Description
Implement the `LLMRouter` that provides automatic fallback between providers, enrich the health endpoint with LLM status, and implement mock mode for development without API keys.

## Acceptance Criteria
- [x] `backend/app/llm/router.py` — `LLMRouter` class:
  - `primary` and `fallback` providers configured from Settings
  - `complete()`: tries primary 3x (exponential backoff 1s/2s/4s), then falls back to fallback provider once
  - If both fail: raise `AllProvidersFailedError` with details from both
  - Logs: `"Using primary: openai"` or `"Primary failed, using fallback: anthropic"`
- [x] `Settings.mock_llm = True` → `LLMRouter` uses `MockLLMProvider` for both slots
- [x] `GET /api/v1/health` enriched: `{llm: {primary: {provider, status, latency_ms}, fallback: {provider, status}}}`
- [x] `LLMRouter` exposed as FastAPI dependency: `get_llm_router() → LLMRouter`
- [x] `AllProvidersFailedError` exception: `{primary_error, fallback_error}`
- [x] Unit test: mock primary to raise, verify fallback called

## Technical Notes
- Exponential backoff: `asyncio.sleep(2**attempt)` for attempts 0,1,2
- Only retry on `is_retryable=True` errors; fail fast on auth errors
- `get_llm_router()` is a singleton (cached with `functools.lru_cache`)
