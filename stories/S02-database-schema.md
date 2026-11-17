# S02 — Database Schema & Models
**Epic**: E0 Foundation | **Priority**: P0 | **Assigned**: architect  
**Depends on**: S01

## Description
Implement the full PostgreSQL database schema using SQLAlchemy 2.0 async ORM. Create Alembic environment and initial migration. All ORM models must exactly match LLD.md §1 SQL schema.

## Acceptance Criteria
- [ ] `backend/app/core/database.py` — async engine + `AsyncSession` factory + `get_db` dependency
- [ ] `backend/app/models/analysis.py` — `Analysis` model: `id` (UUID), `query`, `status`, `result` (JSON), `metadata` (JSON), `error_msg`, `created_at`, `updated_at`
- [ ] `backend/app/models/agent_log.py` — `AgentLog` model: `id`, `analysis_id` (FK), `agent_name`, `step_type`, `content` (JSON), `sequence_no`, `created_at`
- [ ] `backend/app/models/dataset.py` — `Dataset` model + `AnalysisDataset` association table
- [ ] `backend/alembic/` directory initialized with `env.py` targeting async engine
- [ ] `alembic upgrade head` runs cleanly and creates all tables
- [ ] `backend/app/schemas/analysis.py` — Pydantic schemas: `AnalysisCreate`, `AnalysisResponse`, `AnalysisListItem`
- [ ] `backend/app/schemas/agent.py` — `AgentStepSchema`, `AgentLogResponse`
- [ ] Index on `agent_logs(analysis_id, sequence_no)` in migration
- [ ] All models use `mapped_column()` SQLAlchemy 2.0 syntax (not legacy `Column()`)

## Technical Notes
- Use `uuid_generate_v4()` or Python `uuid4()` for PKs
- `result` and `metadata` columns: `JSONB` PostgreSQL type via `sqlalchemy.dialects.postgresql.JSONB`
- Status enum values: `PENDING`, `RUNNING`, `DONE`, `FAILED`
- `updated_at` auto-updates via `onupdate=func.now()`
