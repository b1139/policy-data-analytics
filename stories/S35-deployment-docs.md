# S35 — Deployment & Operations Docs
**Epic**: E8 DevOps | **Priority**: P2 | **Assigned**: devops-engineer  
**Depends on**: S34

## Description
Write the deployment operations guide covering local dev setup, production checklist, monitoring, and scaling notes.

## Acceptance Criteria
- [x] `docs/DEPLOYMENT.md` created with sections:
  - **Quick Start** (3 commands to get running)
  - **Prerequisites** (versions + links)
  - **Configuration** (all env vars table with descriptions)
  - **Local Development** (non-Docker setup for active development)
  - **Production Checklist** (env vars to change, SSL setup, DB backup, rate limiting)
  - **Monitoring** (how to check service health, log inspection commands)
  - **Scaling** (how to run multiple backend replicas, Redis cluster note)
  - **Troubleshooting** (top 5 common issues + fixes)
- [x] All `docker compose` commands verified to work
- [x] Includes `make help` output showing all Makefile targets

## Technical Notes
- Production checklist must include: change `SECRET_KEY`, set `ENVIRONMENT=production`, configure HTTPS
- Log inspection: `docker compose logs -f backend --since 1h`
