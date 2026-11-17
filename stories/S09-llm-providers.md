# S09 — OpenAI + Anthropic Integration
**Epic**: E2 LLM Integration | **Priority**: P0 | **Assigned**: llm-integration-dev  
**Depends on**: S08

## Description
Implement the two concrete LLM providers: OpenAI GPT-4o and Anthropic Claude 3.5 Sonnet. Both must implement `AbstractLLMProvider` and behave identically from the caller's perspective.

## Acceptance Criteria
- [x] `backend/app/llm/gemini_provider.py` — `GeminiProvider(AbstractLLMProvider)`
  - Model: configurable via `Settings.gemini_model` (default: `gemini-1.5-flash`)
  - `complete()`: uses `langchain_google_genai.ChatGoogleGenerativeAI`
  - `json_mode=True` → passes `response_mime_type="application/json"`
  - `health_check()`: sends 1-token completion, returns True/False
- [x] `backend/app/llm/bedrock_provider.py` — `BedrockProvider(AbstractLLMProvider)`
  - Model: configurable via `Settings.bedrock_model_id` (default: `anthropic.claude-3-5-sonnet-20240620-v1:0`)
  - `complete()`: uses `langchain_aws.ChatBedrockConverse`
  - `json_mode=True` → appends JSON instruction
  - `health_check()`: sends 1-token completion, returns True/False
- [x] `backend/app/llm/openai_provider.py` — `OpenAIProvider(AbstractLLMProvider)`
  - Model: configurable via `Settings.openai_model` (default: `gpt-4o`)
  - `complete()`: uses `langchain_openai.ChatOpenAI` under the hood
  - `json_mode=True` → passes `response_format={"type": "json_object"}`
  - `health_check()`: sends 1-token completion, returns True/False
- [x] `backend/app/llm/anthropic_provider.py` — `AnthropicProvider(AbstractLLMProvider)`
  - Model: configurable via `Settings.anthropic_model` (default: `claude-3-5-sonnet-20241022`)
  - `complete()`: uses `langchain_anthropic.ChatAnthropic`
  - `json_mode=True` → appends "Respond with valid JSON only." to system message
  - `health_check()`: sends 1-token completion, returns True/False
- [x] Both providers: log `provider`, `model`, `input_tokens`, `output_tokens`, `latency_ms` on every call
- [x] Both providers: raise `LLMProviderError` (custom exception) on API failure (not raw API exception)
- [x] `LLMProviderError` has: `provider`, `original_error`, `is_retryable` attributes
- [x] Keys never appear in logs (mask: `sk-...****`, `AIza...****`, `AKIA...****`)

## Technical Notes
- LangChain adapts messages format for both providers automatically
- OpenAI rate limits: catch `openai.RateLimitError` → `is_retryable=True`
- Anthropic overloaded: catch `anthropic.APIStatusError` with status 529 → `is_retryable=True`
