# S37 — ARCHITECTURE.md
**Epic**: E9 Docs | **Priority**: P1 | **Assigned**: doc-writer  
**Depends on**: S15

## Description
Write the ARCHITECTURE.md that explains the system design, agent architecture, and key technical decisions. Must reflect the actual implementation.

## Acceptance Criteria
- [ ] `ARCHITECTURE.md` with sections:
  - **System Context** — Mermaid context diagram
  - **Component Architecture** — description of each major component
  - **LangGraph Agent Flow** — Mermaid stateDiagram for coordinator→extraction→analytics
  - **Database Schema** — ER diagram (Mermaid ERD or described tables)
  - **API Reference** — all endpoints with request/response JSON examples
  - **WebSocket Protocol** — message types with JSON examples (matches LLD.md §7)
  - **LLM Integration** — provider abstraction explained, fallback mechanism
  - **Data Source Integration** — registry pattern, adding new sources
  - **Design Decisions** — 6+ decisions with context, options considered, choice, trade-offs
  - **Scalability Considerations** — bottlenecks, horizontal scaling approach
- [ ] Design decisions must include: LangGraph choice, FastAPI choice, PostgreSQL JSONB, Plotly server-side, mock data approach
- [ ] All diagrams render correctly on GitHub

## Technical Notes
- Base design decisions on HLD.md §8 and LLD.md §8 (expand with implementation learnings)
- Note any deviations from original design in an "Implementation Notes" section
