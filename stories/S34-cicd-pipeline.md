# S34 — CI/CD Pipeline (GitHub Actions)
**Epic**: E8 DevOps | **Priority**: P1 | **Assigned**: devops-engineer  
**Depends on**: S33, S29

## Description
Implement GitHub Actions CI/CD workflows: a test pipeline that runs on every PR and a deploy pipeline that builds/pushes Docker images on merge to main.

## Acceptance Criteria
- [ ] `.github/workflows/test.yml` — triggers on `push` to any branch + `pull_request` to `main`:
  - Job `backend-test`:
    - Service containers: postgres:15 + redis:7
    - `pip install -r requirements.txt`
    - `alembic upgrade head`
    - `pytest tests/ --cov=app --cov-fail-under=75`
    - Upload coverage to Codecov (or just artifact)
  - Job `frontend-test`:
    - `npm ci`
    - `npm run lint`
    - `npm test -- --coverage`
  - Job `lint`:
    - `ruff check backend/`
    - `ruff format --check backend/`
- [ ] `.github/workflows/deploy.yml` — triggers on push to `main` after tests pass:
  - Build + push backend image to `ghcr.io/{owner}/policy-analytics-backend:latest`
  - Build + push frontend image to `ghcr.io/{owner}/policy-analytics-frontend:latest`
  - Deploy step: `echo "Deploy images to staging environment"` (placeholder)
- [ ] `.github/dependabot.yml` — weekly updates: `pip`, `npm`, `docker`
- [ ] All workflows use `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`
- [ ] CI status badge in README

## Technical Notes
- GitHub Secrets needed: `GHCR_TOKEN` for image push
- `MOCK_LLM=true` and `USE_MOCK_DATA_SOURCES=true` in CI env vars
- Backend tests use `TEST_DATABASE_URL=postgresql+asyncpg://...` service container
