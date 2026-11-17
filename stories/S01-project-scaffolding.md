# S01 — Project Scaffolding & Monorepo
**Epic**: E0 Foundation | **Priority**: P0 | **Assigned**: architect  
**Depends on**: none

## Description
Initialize the full monorepo structure for `policy-analytics-platform/`. Set up Next.js 14 frontend and FastAPI backend with all configuration files, ensuring the project can be cloned and run with a single Docker Compose command after adding env vars.

## Acceptance Criteria
- [ ] Root directory `policy-analytics-platform/` created with `frontend/` and `backend/` subdirectories
- [ ] `frontend/` bootstrapped with Next.js 14 App Router + TypeScript strict mode + Tailwind + shadcn/ui
- [ ] `backend/` has full directory structure matching LLD.md §2 (all empty `__init__.py` where needed)
- [ ] `backend/app/main.py` runs: `uvicorn app.main:app` starts without errors
- [ ] `backend/requirements.txt` matches TECH_STACK.md exact versions
- [ ] `frontend/package.json` matches TECH_STACK.md exact versions
- [ ] `pyproject.toml` has ruff config + pytest config sections
- [ ] `.env.example` lists every required env var with a description comment
- [ ] `Makefile` has targets: `start`, `stop`, `test`, `migrate`, `lint`, `shell-backend`
- [ ] `frontend/app/layout.tsx` and `frontend/app/page.tsx` exist and compile

## Technical Notes
- Use `npx create-next-app@14` with `--typescript --tailwind --app` flags
- Use `shadcn/ui init` command to set up component library
- Backend `main.py` must register CORS middleware allowing `localhost:3000`
- Include `backend/app/core/config.py` with minimal `Settings` class (expand in S04)
