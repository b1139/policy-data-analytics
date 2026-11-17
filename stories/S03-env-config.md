# S03 — Environment & Config Management
**Epic**: E0 Foundation | **Priority**: P0 | **Assigned**: devops-engineer  
**Depends on**: S01

## Description
Finalize environment configuration: complete `.env.example`, complete Pydantic Settings class with all required vars, and create the `Makefile` with all standard dev commands.

## Acceptance Criteria
- [ ] `.env.example` has sections: LLM Providers, Database, Redis, Data Sources, App Settings
- [ ] Every env var has a one-line comment explaining its purpose and format
- [ ] `backend/app/core/config.py` `Settings` class covers all vars from `.env.example`
- [ ] Settings uses `pydantic-settings` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`
- [ ] `Settings.validate_llm_config()` validator: warns if both LLM keys absent (but doesn't error — allows mock mode)
- [ ] `Makefile` targets work: `make start` = `docker compose up -d`, `make test` = runs pytest + jest
- [ ] `make shell-backend` = `docker compose exec backend bash`
- [ ] `.gitignore` includes: `.env`, `*.pyc`, `__pycache__`, `.next/`, `node_modules/`, `*.egg-info/`

## Technical Notes
- Required env vars: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MOCK_LLM`, `PRIMARY_LLM_PROVIDER`, `FALLBACK_LLM_PROVIDER`, `SINGSTAT_API_KEY`, `DATAGOV_API_TOKEN`, `USE_MOCK_DATA_SOURCES`, `SECRET_KEY`, `ENVIRONMENT`, `LOG_LEVEL`, `CORS_ORIGINS`
- `CORS_ORIGINS` is a JSON list string: `'["http://localhost:3000"]'`
