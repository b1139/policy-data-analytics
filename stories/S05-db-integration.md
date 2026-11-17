# S05 — Database Integration
**Epic**: E1 Backend Core | **Priority**: P0 | **Assigned**: backend-dev  
**Depends on**: S04

## Description
Implement async CRUD operations for all three models (Analysis, AgentLog, Dataset) using SQLAlchemy 2.0. These are the data access methods that all services and agents will use.

## Acceptance Criteria
- [ ] `backend/app/crud/analysis.py`:
  - `create_analysis(db, query) → Analysis`
  - `get_analysis(db, id) → Analysis | None`
  - `list_analyses(db, skip, limit) → list[Analysis]`
  - `update_analysis_status(db, id, status, result?, error_msg?) → Analysis`
  - `delete_analysis(db, id) → bool`
- [ ] `backend/app/crud/agent_log.py`:
  - `create_agent_log(db, analysis_id, agent_name, step_type, content, seq_no) → AgentLog`
  - `list_agent_logs(db, analysis_id) → list[AgentLog]`
- [ ] `backend/app/crud/dataset.py`:
  - `get_or_create_dataset(db, source, source_id, data_hash, ...) → (Dataset, created: bool)`
  - `link_dataset_to_analysis(db, analysis_id, dataset_id)`
- [ ] All CRUD functions use `async with session` and `await session.commit()`
- [ ] All CRUD functions accept `AsyncSession` as first argument (injected via dep)
- [ ] `alembic upgrade head` confirmed working in test

## Technical Notes
- Use `select()` + `session.execute()` pattern (SQLAlchemy 2.0 style)
- Use `session.refresh(obj)` after create to load server-side defaults
- Soft delete: `delete_analysis` sets `status=DELETED` (don't actually delete rows)
