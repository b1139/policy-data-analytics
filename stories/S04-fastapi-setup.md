# S04 — FastAPI Application Bootstrap
**Epic**: E1 Backend Core | **Priority**: P0 | **Assigned**: backend-dev  
**Depends on**: S01, S02, S03

## Description
Complete the FastAPI application factory: lifespan events (startup/shutdown), middleware, router mounting, structured logging, and the health check endpoint. This is the runnable backend skeleton.

## Acceptance Criteria
- [x] `backend/app/main.py` creates FastAPI app with `title`, `version`, `description`
- [x] Lifespan context manager: creates DB tables on startup, closes connections on shutdown
- [x] CORS middleware configured from `Settings.cors_origins`
- [x] All routers mounted under `/api/v1/` prefix
- [x] `GET /api/v1/health` returns `{status: "ok", db: "ok/error", redis: "ok/error", timestamp: ISO8601}`
- [x] Structured logging: JSON log lines with `level`, `message`, `timestamp`, `request_id`
- [x] Request ID middleware: adds `X-Request-ID` header to every response
- [x] `uvicorn app.main:app --reload` starts without errors after `pip install -r requirements.txt`
- [x] `/docs` (Swagger UI) accessible and shows all registered routes

## Technical Notes
- Use `@asynccontextmanager` lifespan pattern (FastAPI 0.111+ recommended approach)
- Redis connection checked in health endpoint (non-fatal if down)
- Log format: `%(asctime)s %(levelname)s %(name)s %(message)s`
