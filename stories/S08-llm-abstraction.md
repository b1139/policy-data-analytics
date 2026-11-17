# S08 — LLM Provider Abstraction Layer
**Epic**: E2 LLM Integration | **Priority**: P0 | **Assigned**: llm-integration-dev  
**Depends on**: S04

## Description
Create the abstract base class and data models for LLM provider integration. All LLM calls in the application flow through this interface — it's the single point of model selection, error handling, and observability.

## Acceptance Criteria
- [x] `backend/app/llm/base.py` — `AbstractLLMProvider` ABC with methods: `complete()`, `health_check()`
- [x] `complete(messages: list[dict], **kwargs) → LLMResponse` signature (must be async)
- [x] `LLMResponse` dataclass: `content: str`, `model: str`, `provider: str`, `usage: dict`, `latency_ms: float`
- [x] `usage` dict: `{input_tokens: int, output_tokens: int, total_tokens: int}`
- [x] `MockLLMProvider` in `backend/app/llm/mock_provider.py`:
  - Returns deterministic responses based on message content keyword matching
  - Has configurable delay (`mock_latency_ms` param) for testing
  - `health_check()` always returns `True`
- [x] `backend/app/llm/__init__.py` exports: `AbstractLLMProvider`, `LLMResponse`, `MockLLMProvider`
- [x] All implementations in `llm/` module use the same `messages` format: `[{role, content}]`

## Technical Notes
- `messages` format: list of `{"role": "system"|"user"|"assistant", "content": str}`
- `kwargs` for `complete()`: `temperature=0.7`, `max_tokens=1000`, `json_mode=False`
- `json_mode=True` → instructs provider to return valid JSON string in `content`
