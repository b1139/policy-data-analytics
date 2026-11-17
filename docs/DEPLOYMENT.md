# Agentic Policy Data Analytics Platform — Deployment & Operations Guide

This guide provides end-to-end instructions for deploying, configuring, monitoring, and troubleshooting the **Agentic Policy Data Analytics Platform** across local development, staging, and production environments.

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Makefile Target Reference](#makefile-target-reference)
4. [Configuration & Environment Variables](#configuration--environment-variables)
5. [Local Development (Non-Docker Setup)](#local-development-non-docker-setup)
6. [Docker Deployment](#docker-deployment)
7. [Production Checklist](#production-checklist)
8. [Monitoring & Health Probes](#monitoring--health-probes)
9. [Scaling & High Availability](#scaling--high-availability)
10. [Troubleshooting Guide](#troubleshooting-guide)

---

## Quick Start

Get the complete platform running with **3 commands**:

```bash
# 1. Copy template environment configuration
cp .env.example .env

# 2. Build and launch all services in detached mode
docker compose up --build -d

# 3. Verify that all platform services are healthy
curl -s http://localhost/api/v1/health | grep '"status":"ok"'
```

Once running, access the platform endpoints:
- **Web User Interface**: [http://localhost](http://localhost) (via Nginx proxy on port 80)
- **FastAPI Backend Documentation (Swagger UI)**: [http://localhost/docs](http://localhost/docs) or [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Documentation**: [http://localhost/redoc](http://localhost/redoc)
- **Health Check Endpoint**: [http://localhost/api/v1/health](http://localhost/api/v1/health)

To stop all services:
```bash
docker compose down
```

---

## Prerequisites

Ensure your host environment meets or exceeds the required versions:

| Component | Minimum Version | Recommended Version | Download & Documentation |
|-----------|-----------------|---------------------|--------------------------|
| **Docker Engine** | `24.0.0+` | `26.0.0+` | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| **Docker Compose** | `v2.20.0+` | `v2.27.0+` | [docs.docker.com/compose/install](https://docs.docker.com/compose/install/) |
| **Python** | `3.15.0` | `3.15.2+` | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js** | `18.18.0` (LTS) | `20.12.0+` (LTS) | [nodejs.org/en/download](https://nodejs.org/en/download/) |
| **npm** | `9.0.0+` | `10.5.0+` | Bundled with Node.js |
| **GNU Make** | `3.81+` | `4.3+` | Pre-installed on macOS/Linux |
| **PostgreSQL Client (`psql`)** *(optional)* | `15.0+` | `15.5+` | [postgresql.org/download](https://www.postgresql.org/download/) |
| **Redis CLI (`redis-cli`)** *(optional)* | `7.0+` | `7.2+` | [redis.io/download](https://redis.io/download/) |

---

## Makefile Target Reference

A centralized `Makefile` is provided at the repository root to simplify developer and CI workflows. Run `make help` to inspect available commands:

```text
Agentic Policy Data Analytics Platform - Command Center
Available commands:
  make start          Start all services (docker compose up -d)
  make stop           Stop all running services (docker compose down)
  make test           Run backend and frontend tests
  make test-backend   Run backend pytest suite
  make test-frontend  Run frontend jest suite
  make migrate        Run database migrations (alembic upgrade head)
  make lint           Run lint checks (ruff + eslint)
  make logs           Follow container logs (docker compose logs -f)
  make shell          Open an interactive bash shell in backend service
  make shell-backend  Open an interactive bash shell in backend service
```

### Command Descriptions

- `make start`: Executes `docker compose up -d` to bring up PostgreSQL, Redis, FastAPI backend, Next.js frontend, and Nginx.
- `make stop`: Executes `docker compose down` to gracefully stop and remove containers and internal networks while preserving persistent volumes.
- `make test`: Runs both Python backend tests (`pytest`) and Next.js frontend tests (`jest`).
- `make test-backend`: Runs pytest on the FastAPI application suite.
- `make test-frontend`: Runs the Jest test runner inside the frontend workspace.
- `make migrate`: Runs database schema migrations via Alembic (`cd backend && alembic upgrade head`).
- `make lint`: Executes code quality and style linters (`ruff check` + `ruff format` for Python, `eslint` for TypeScript/React).
- `make logs`: Attaches an active log tail (`docker compose logs -f`) across all platform containers.
- `make shell`: Launches an interactive bash shell inside the running `backend` container for debugging.

---

## Configuration & Environment Variables

All platform settings are managed through environment variables adhering to the Twelve-Factor App methodology. Variables are loaded from `.env` in the root directory (or injected by container orchestrators such as Kubernetes / ECS).

### Comprehensive Environment Variables Table

| Variable Name | Description | Default Value | Required in Production | Category |
|---------------|-------------|---------------|------------------------|----------|
| `ENVIRONMENT` | Runtime deployment stage (`development`, `staging`, `production`, `testing`) | `development` | **Yes** (set to `production`) | App Core |
| `PROJECT_NAME` | Platform title displayed in API schema and documentation | `Agentic Policy Data Analytics Platform` | No | App Core |
| `SECRET_KEY` | Cryptographic secret key used for signing session tokens and internal HMACs (min 32 characters) | `dev-insecure-secret-key-min-32-chars-long-12345` | **Yes** (must be high-entropy random string) | Security |
| `LOG_LEVEL` | Application logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | `INFO` | No (set to `INFO` or `WARNING`) | Logging |
| `CORS_ORIGINS` | JSON array or comma-separated string of trusted origins allowed to query the API | `["http://localhost:3000","http://127.0.0.1:3000"]` | **Yes** (set to production domain) | Security |
| `API_V1_STR` | URL routing prefix for REST API version 1 | `/api/v1` | No | App Core |
| `DATABASE_URL` | SQLAlchemy async connection string (`postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db>`) | `postgresql+asyncpg://policy_user:policy_pass@localhost:5432/policy_analytics` | **Yes** | Database |
| `POSTGRES_USER` | PostgreSQL superuser/application user | `policy_user` | **Yes** | Database |
| `POSTGRES_PASSWORD` | PostgreSQL database user password | `policy_pass` | **Yes** (use strong credentials) | Database |
| `POSTGRES_DB` | PostgreSQL primary database name | `policy_analytics` | **Yes** | Database |
| `REDIS_URL` | Redis connection URL for query caching, agent state checkpoints, and pub/sub | `redis://localhost:6379/0` | **Yes** | Caching |
| `MOCK_LLM` | Toggle offline deterministic mock LLM provider (bypasses live API keys and network calls) | `false` | **Yes** (set to `false`) | LLM Engine |
| `PRIMARY_LLM_PROVIDER` | Primary foundational LLM provider (`gemini`, `bedrock`, `openai`, `anthropic`) | `gemini` | **Yes** | LLM Engine |
| `FALLBACK_LLM_PROVIDER` | Fallback foundational LLM provider triggered if primary fails or is rate-limited | `bedrock` | **Yes** | LLM Engine |
| `GEMINI_API_KEY` | Google AI Studio / Gemini API secret token | `""` | Yes (if Gemini provider used) | LLM Credentials |
| `GEMINI_MODEL` | Google Gemini foundation model name | `gemini-1.5-flash` | No | LLM Engine |
| `BEDROCK_API_KEY` | Amazon Bedrock bearer token (if using direct token auth) | `""` | Conditional | LLM Credentials |
| `AWS_BEARER_TOKEN_BEDROCK` | Alternative Bedrock bearer token override | `""` | Conditional | LLM Credentials |
| `AWS_ACCESS_KEY_ID` | AWS IAM access key ID for Bedrock API access | `""` | Yes (if Bedrock IAM used) | AWS Credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret access key for Bedrock API access | `""` | Yes (if Bedrock IAM used) | AWS Credentials |
| `AWS_REGION` | AWS region where Amazon Bedrock foundation models are hosted | `ap-south-2` | Yes (if Bedrock used) | AWS Config |
| `AWS_DEFAULT_REGION` | AWS default region fallback | `ap-south-2` | No | AWS Config |
| `BEDROCK_MODEL_ID` | Amazon Bedrock model identifier string | `anthropic.claude-3-5-sonnet-20240620-v1:0` | No | LLM Engine |
| `OPENAI_API_KEY` | OpenAI secret API key (`sk-...`) | `""` | Yes (if OpenAI provider used) | LLM Credentials |
| `OPENAI_MODEL` | OpenAI foundation model identifier | `gpt-4o` | No | LLM Engine |
| `ANTHROPIC_API_KEY` | Anthropic Claude secret API key (`sk-ant-...`) | `""` | Yes (if Anthropic direct used) | LLM Credentials |
| `ANTHROPIC_MODEL` | Anthropic Claude model identifier | `claude-3-5-sonnet-20241022` | No | LLM Engine |
| `USE_MOCK_DATA_SOURCES` | Toggle local synthetic mock data fixtures instead of live remote Singapore APIs | `false` | **Yes** (set to `false`) | Data Sources |
| `SINGSTAT_MCP_ENABLED` | Toggle SingStat Model Context Protocol (MCP) server integration | `true` | No | Data Sources |
| `SINGSTAT_MCP_URL` | SingStat MCP server endpoint URL | `https://www.singstat.gov.sg/data-tools-services/singstat-mcp` | No | Data Sources |
| `SINGSTAT_API_KEY` | SingStat developer API subscription key | `""` | Yes (for live data queries) | Data Sources |
| `DATAGOV_API_TOKEN` | Data.gov.sg developer API token | `""` | Yes (for live data queries) | Data Sources |
| `NEXT_PUBLIC_API_URL` | Backend REST API base URL accessible from frontend client | `http://localhost:8000` | **Yes** (e.g. `https://analytics.yourdomain.gov.sg`) | Frontend |
| `NEXT_PUBLIC_WS_URL` | Backend WebSocket streaming URL for real-time agent updates | `ws://localhost:8000` | **Yes** (e.g. `wss://analytics.yourdomain.gov.sg`) | Frontend |

---

## Local Development (Non-Docker Setup)

For rapid day-to-day code iteration with hot-reloading across the Python backend and Next.js frontend without rebuilding Docker containers:

### 1. Start Dependent Services (Postgres & Redis)
You can use Docker solely for stateful backing services:
```bash
docker compose up -d postgres redis
```
This binds PostgreSQL to `localhost:5432` and Redis to `localhost:6379`.

### 2. Configure Python Virtual Environment & Backend
```bash
cd backend

# Create and activate Python 3.15 virtual environment
python3.15 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run database schema migrations
alembic upgrade head

# Start FastAPI development server with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend API is now accessible at `http://localhost:8000` and docs at `http://localhost:8000/docs`.

### 3. Configure Frontend Development Server
In a separate terminal:
```bash
cd frontend

# Install Node dependencies
npm install

# Run Next.js in development mode with Turbopack / Fast Refresh
npm run dev
```
The frontend UI is now running at `http://localhost:3000`.

### 4. Running Tests & Quality Checks Locally
```bash
# Backend pytest suite
pytest backend/tests

# Frontend Jest suite
cd frontend && npm test -- --watchAll=false

# Lint checks
ruff check backend
ruff format --check backend
cd frontend && npm run lint
```

---

## Docker Deployment

The application includes production-ready multi-stage Docker builds designed to minimize attack surface and image size (Backend < 500MB, Frontend < 300MB).

### Container Orchestration Topology

```mermaid
flowchart TD
    Client["Browser / Client (Port 80 / 443)"] --> Nginx["Nginx Reverse Proxy (:80)"]
    Nginx -->|/api/* & /docs| Backend["FastAPI Backend (:8000)"]
    Nginx -->|/ws/*| BackendWS["FastAPI WebSockets (:8000)"]
    Nginx -->|/*| Frontend["Next.js Standalone (:3000)"]
    Backend --> Postgres[("PostgreSQL 15 (:5432)")]
    Backend --> Redis[("Redis 7 (:6379)")]
```

### Container Lifecycle & Health Dependency

`docker-compose.yml` ensures that:
1. `postgres` starts and completes its internal `pg_isready` healthcheck.
2. `redis` starts and passes `redis-cli ping`.
3. `backend` starts only after both `postgres` and `redis` report healthy status (`condition: service_healthy`).
4. On backend startup, the container entrypoint automatically executes `alembic upgrade head` before spawning `uvicorn`.
5. `frontend` starts and connects to `backend`.
6. `nginx` starts as the unified edge gateway routing `/api/*` and `/ws/*` to the backend and `/*` to the frontend.

### Isolated Test Environment (`docker-compose.test.yml`)
For automated CI or local integration testing in isolation without disturbing existing databases:
```bash
# Run isolated test stack (uses dedicated postgres-test:5433 and redis-test:6380)
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

---

## Production Checklist

Before exposing the platform in staging or production, execute the following security and operational checks:

### 1. Environment & Secrets Hardening
- [ ] **Generate High-Entropy `SECRET_KEY`**:
  ```bash
  openssl rand -hex 32
  ```
  Set this value in production `.env` or AWS Secrets Manager / Vault. Never use the default development string.
- [ ] **Set `ENVIRONMENT=production`**: Disables verbose internal debug messages in error payloads.
- [ ] **Disable Mock Modes**: Ensure `MOCK_LLM=false` and `USE_MOCK_DATA_SOURCES=false`.
- [ ] **Configure Valid API Credentials**: Provide verified keys for `GEMINI_API_KEY`, `BEDROCK_API_KEY` (or AWS IAM keys), `SINGSTAT_API_KEY`, and `DATAGOV_API_TOKEN`.
- [ ] **Restrict CORS Origins**: Update `CORS_ORIGINS` to contain only your authorized domains:
  ```env
  CORS_ORIGINS=["https://analytics.yourdomain.gov.sg"]
  ```

### 2. SSL/TLS Termination with Nginx
In production, place Nginx behind a valid SSL/TLS certificate (e.g., Let's Encrypt / Certbot or corporate PKI).

Example production Nginx SSL configuration snippet:
```nginx
server {
    listen 80;
    server_name analytics.yourdomain.gov.sg;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name analytics.yourdomain.gov.sg;

    ssl_certificate /etc/letsencrypt/live/analytics.yourdomain.gov.sg/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.yourdomain.gov.sg/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS (Strict Transport Security)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Proxy routes to backend and frontend upstreams...
}
```

### 3. Rate Limiting Configuration
Add Nginx connection and request rate limiting zones to prevent API abuse or denial of service on computationally intensive agent endpoints:
```nginx
# Define rate limiting zones in http context
limit_req_zone $binary_remote_addr zone=api_general:10m rate=100r/m;
limit_req_zone $binary_remote_addr zone=analysis_heavy:10m rate=10r/m;

# Apply to analysis trigger endpoint
location /api/v1/analysis {
    limit_req zone=analysis_heavy burst=5 nodelay;
    proxy_pass http://backend_upstream;
}
```

### 4. PostgreSQL Automated Backup & Restore Procedures

#### Automated Daily Backup Script (`scripts/backup_postgres.sh`)
Create an executable backup script:
```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/postgres"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/policy_analytics_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting PostgreSQL database backup..."
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-policy_user}" -d "${POSTGRES_DB:-policy_analytics}" | gzip > "${BACKUP_FILE}"

echo "[$(date)] Backup successfully saved to ${BACKUP_FILE} (Size: $(du -h "${BACKUP_FILE}" | cut -f1))"

# Prune backups older than retention window
find "${BACKUP_DIR}" -name "policy_analytics_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "[$(date)] Expired backups older than ${RETENTION_DAYS} days pruned."
```

Configure a daily cron job (`crontab -e`):
```text
0 2 * * * /path/to/PolicyDataAnalytics/scripts/backup_postgres.sh >> /var/log/cron-db-backup.log 2>&1
```

#### Database Restoration Procedure
To restore the database from a compressed backup archive:
```bash
# 1. Decompress and restore into PostgreSQL
gunzip -c /var/backups/postgres/policy_analytics_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U policy_user -d policy_analytics

# 2. Run schema migration check
docker compose exec -T backend alembic upgrade head
```

---

## Monitoring & Health Probes

### Health Check Endpoint

The platform exposes a single unified health inspection endpoint for container probes, load balancers, and external status monitoring:

**System Health Probe**: `GET /api/v1/health`
- Verifies PostgreSQL database connectivity (`SELECT 1`).
- Verifies Redis connectivity (`PING` -> `PONG`).
- Verifies primary and fallback LLM connectivity (cached for 60s to prevent spamming external APIs).
- Supports query parameters: `?check_llm=false` (omit LLM probe for lightweight liveness checks) and `?force_llm_check=true` (bypass 60s cache).
- Example response:
  ```json
  {
    "status": "ok",
    "db": "ok",
    "redis": "ok",
    "llm": {
      "primary": {
        "provider": "gemini",
        "model": "gemini-1.5-flash",
        "status": "ok",
        "latency_ms": 112.4
      },
      "fallback": {
           "provider": "bedrock",
           "model": "anthropic.claude-3-5-sonnet-20240620-v1:0",
           "status": "ok",
           "latency_ms": 145.8
         }
       },
       "timestamp": "2026-11-16T12:00:00.000000+00:00",
       "environment": "production"
     }
     ```

2. **Nginx Ingress Probe**: `GET /nginx-health`
   - Returns HTTP `200 OK` with payload `healthy\n`. Does not flood access logs.

### Log Inspection Commands

Utilize Docker Compose log filtering for real-time observability:

```bash
# Follow backend logs from the last 1 hour
docker compose logs -f backend --since 1h

# Follow frontend Next.js logs with timestamps
docker compose logs -f -t frontend

# Follow Nginx edge access and error logs
docker compose logs -f nginx

# Check database query and connection logs
docker compose logs --tail=100 postgres

# Check Redis memory and client connections
docker compose logs --tail=100 redis

# Real-time resource usage across all containers
docker stats
```

---

## Scaling & High Availability

### Scaling Backend Replicas

The backend FastAPI application is stateless; query status and agent execution checkpoints are persisted in PostgreSQL and Redis. This architecture allows effortless horizontal scaling behind Nginx.

```mermaid
flowchart LR
    Nginx["Nginx Reverse Proxy"] --> B1["Backend Worker 1 (:8000)"]
    Nginx --> B2["Backend Worker 2 (:8000)"]
    Nginx --> B3["Backend Worker 3 (:8000)"]
    B1 --> DB[("PostgreSQL")]
    B2 --> DB
    B3 --> DB
    B1 --> Redis[("Redis")]
    B2 --> Redis
    B3 --> Redis
```

To run multiple backend replicas:

1. In `docker-compose.yml`, remove or comment out `container_name: policy_analytics_backend` (Docker requires unique container names when scaling).
2. Launch the desired number of backend instances:
   ```bash
   docker compose up -d --scale backend=3
   ```
3. Docker's internal embedded DNS automatically resolves `backend:8000` across all 3 running containers in a round-robin distribution, balanced by Nginx's `upstream backend_upstream`.

### Redis High Availability & Clustering
For high-volume production deployments:
- **Managed Redis**: Utilize AWS ElastiCache for Redis (with Multi-AZ and auto-failover enabled) or Redis Cloud.
- **Self-Hosted Sentinel**: In self-hosted setups, configure Redis Sentinel with a primary and two replica instances. Update `REDIS_URL` to point to the active master endpoint.

### Database Connection Management
- The backend uses SQLAlchemy 2.0 async engine with connection pooling (`pool_size=10`, `max_overflow=20`).
- If scaling backend replicas beyond 5 nodes, deploy **PgBouncer** between FastAPI and PostgreSQL to prevent exhausting PostgreSQL connection limits (`max_connections = 100`).

---

## Troubleshooting Guide

The top 5 most common operational issues and verified resolutions:

### 1. Port Conflicts (`Address already in use: 80`, `5432`, `6379`, `3000`, `8000`)
- **Symptom**: `docker compose up` fails with:
  `Error response from daemon: driver failed programming external connectivity on endpoint ... bind: address already in use`
- **Cause**: A host process (e.g. system PostgreSQL, standalone Redis server, Apache, or a previous development server) is already bound to that port.
- **Resolution**:
  1. Identify the blocking process:
     ```bash
     # macOS / Linux
     lsof -i :5432
     lsof -i :80
     ```
  2. Terminate the conflicting local service (e.g., `brew services stop postgresql` or `kill -9 <PID>`).
  3. Alternatively, remap host ports in your `.env` or create a `docker-compose.override.yml`:
     ```yaml
     services:
       postgres:
         ports:
           - "5433:5432"
     ```

### 2. Database Connection Refused
- **Symptom**: Backend logs display:
  `Is the server running on host "postgres" and accepting TCP/IP connections on port 5432?`
- **Cause**: The PostgreSQL container is still initializing, failed password validation, or the named Docker network bridge is disconnected.
- **Resolution**:
  1. Inspect PostgreSQL container status and logs:
     ```bash
     docker compose ps postgres
     docker compose logs postgres --tail 50
     ```
  2. Verify PostgreSQL health manually:
     ```bash
     docker compose exec postgres pg_isready -U policy_user -d policy_analytics
     ```
  3. If credentials were changed in `.env` after volume creation, remove the stale volume and re-initialize:
     ```bash
     docker compose down -v
     docker compose up -d
     ```

### 3. Redis Connectivity / Authentication Error
- **Symptom**: Backend logs report:
  `ConnectionRefusedError: [Errno 111] Connect call failed ('redis', 6379)`
- **Cause**: Redis container crashed or `REDIS_URL` inside the container points to `localhost` instead of the Docker DNS hostname `redis`.
- **Resolution**:
  1. Check Redis container health:
     ```bash
     docker compose exec redis redis-cli ping
     # Must return: PONG
     ```
  2. Ensure `.env` or container environment defines `REDIS_URL=redis://redis:6379/0` (inside Docker network), not `localhost`.

### 4. Missing LLM Credentials Warning
- **Symptom**: Healthcheck reports `"llm": {"status": "error"}` or application logs show:
  `UserWarning: No LLM provider credentials configured ... while MOCK_LLM=False`
- **Cause**: `MOCK_LLM=false` is set, but neither `GEMINI_API_KEY`, Bedrock AWS credentials, nor OpenAI/Anthropic keys were provided in `.env`.
- **Resolution**:
  1. For offline development and verification, set `MOCK_LLM=true` in `.env`.
  2. For live LLM calls, populate valid credentials in `.env`:
     ```env
     MOCK_LLM=false
     PRIMARY_LLM_PROVIDER=gemini
     GEMINI_API_KEY=your_actual_gemini_api_key_here
     ```
  3. Restart the backend service:
     ```bash
     docker compose restart backend
     ```

### 5. Container Out of Memory (OOM) During Frontend Build or Heavy Analysis
- **Symptom**: Next.js build terminates with `SIGKILL` / `Killed`, or Docker exits with code `137`.
- **Cause**: Docker Desktop on macOS/Windows defaults to 2GB memory allocation, which is insufficient for running concurrent Next.js standalone builds and statistical pandas transformations.
- **Resolution**:
  1. In Docker Desktop Settings -> **Resources** -> Increase Memory limit to at least **4 GB** (8 GB recommended).
  2. For constrained production virtual machines, configure swap space or add memory limits with reservation in `docker-compose.yml`:
     ```yaml
     services:
       frontend:
         deploy:
           resources:
             limits:
               memory: 1024M
     ```

---

*For further architecture details and system design specifications, refer to [HLD.md](../HLD.md) and [LLD.md](../LLD.md).*
