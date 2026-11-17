# S33 — Docker & Docker Compose Setup
**Epic**: E8 DevOps | **Priority**: P0 | **Assigned**: devops-engineer  
**Depends on**: S06, S24

## Description
Containerize both frontend and backend with multi-stage Dockerfiles, create a Docker Compose configuration that runs the full stack with one command, and add an Nginx reverse proxy.

## Acceptance Criteria
- [ ] `backend/Dockerfile` — multi-stage:
  - Stage 1 (`builder`): `python:3.15-slim`, install requirements
  - Stage 2 (`runtime`): copy app + non-root user `appuser` (UID 1000)
  - Entrypoint: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - Image size < 500MB
- [ ] `frontend/Dockerfile` — multi-stage:
  - Stage 1 (`builder`): `node:18-alpine`, `npm ci`, `npm run build`
  - Stage 2 (`runner`): `node:18-alpine`, copy `.next/standalone`, expose 3000
  - Image size < 300MB
- [ ] `docker-compose.yml` — services: `frontend`, `backend`, `postgres`, `redis`, `nginx`
  - `postgres`: `postgres:15-alpine`, volume `postgres_data`
  - `redis`: `redis:7-alpine`, volume `redis_data`
  - `backend`: `depends_on: {postgres: {condition: service_healthy}, redis: {condition: service_healthy}}`
  - postgres healthcheck: `pg_isready -U $POSTGRES_USER`
  - redis healthcheck: `redis-cli ping`
- [ ] `nginx.conf` — routes `/api/*` and `/ws/*` → `backend:8000`; `/*` → `frontend:3000`
- [ ] `docker-compose.test.yml` — uses different ports (5433, 6380) + no nginx
- [ ] `docker compose up` from fresh clone (with `.env`) produces working system in <5 minutes

## Technical Notes
- Backend: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` env vars
- Frontend: `output: "standalone"` in `next.config.ts`
- Nginx: `proxy_read_timeout 300s` for long-running analysis requests
