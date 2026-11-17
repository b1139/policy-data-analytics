# S36 — README.md & Setup Guide
**Epic**: E9 Docs | **Priority**: P0 | **Assigned**: doc-writer  
**Depends on**: S33

## Description
Write the main project README.md that meets all submission requirements. Must be clear enough for someone unfamiliar with the project to run it in under 10 minutes.

## Acceptance Criteria
- [x] `README.md` at project root with all sections:
  - **Project Overview** — 2-3 sentence description
  - **Architecture Overview** — Mermaid component diagram + brief description
  - **Tech Stack** — table: component, technology, reason (one line each)
  - **Prerequisites** — Docker, Node 18+, Python 3.15+ with version checks
  - **Quick Setup** — 3-command path using `setup.py`
  - **Manual Setup** — step-by-step without script
  - **Running the Application** — start command, URLs, expected output
  - **Running Tests** — backend pytest command, frontend jest command, expected output
  - **Sample Queries** — 5 queries that work with mock data
  - **Project Structure** — annotated directory tree
  - **API Reference** — brief table of endpoints with method/path/description
  - **Environment Variables** — table of all vars, required/optional, description
  - **Troubleshooting** — top 5 issues
- [x] README badges: CI status, coverage
- [x] All commands tested and produce stated output
- [x] No aspirational features documented as if implemented

## Technical Notes
- Mermaid diagram: use `graph TD` for component relationships
- Sample queries must work with `USE_MOCK_DATA_SOURCES=true MOCK_LLM=true`
