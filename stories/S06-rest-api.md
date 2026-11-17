# S06 — Core REST API Endpoints
**Epic**: E1 Backend Core | **Priority**: P0 | **Assigned**: backend-dev  
**Depends on**: S05

## Description
Implement all REST API endpoints for analysis management. Endpoints must be fully typed, return proper Pydantic response models, and include meaningful error handling.

## Acceptance Criteria
- [ ] `POST /api/v1/analysis/start` — body: `{query: str}` → returns `{analysis_id, status, ws_url}`
- [ ] `GET /api/v1/analysis/{id}` — returns full `AnalysisResponse` with nested `agent_logs`
- [ ] `GET /api/v1/analysis/` — paginated: `?skip=0&limit=20` → `{items: [...], total: int}`
- [ ] `GET /api/v1/analysis/{id}/export` — returns JSON file download with `Content-Disposition` header
- [ ] `DELETE /api/v1/analysis/{id}` — soft delete, returns `204 No Content`
- [ ] All endpoints return appropriate HTTP status codes (201, 200, 404, 422, 500)
- [ ] 404 response: `{detail: "Analysis <id> not found"}`
- [ ] `POST /start` triggers background task (actual LangGraph integration wired in S15)
- [ ] Validation: query must be non-empty string, min 10 chars, max 2000 chars
- [ ] `GET /api/v1/analysis/{id}` includes `agent_logs` sorted by `sequence_no`

## Technical Notes
- Use `BackgroundTasks` from FastAPI for async analysis execution
- `ws_url` in start response: `ws://localhost:8000/ws/analysis/{id}`
- Export: JSON with `Content-Disposition: attachment; filename=analysis_{id}.json`
