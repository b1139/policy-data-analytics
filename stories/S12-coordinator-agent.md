# S12 — Data Coordinator Agent
**Epic**: E3 Agents | **Priority**: P0 | **Assigned**: agent-dev  
**Depends on**: S11

## Description
Implement the Data Coordinator agent node. It receives the user's natural language query, uses an LLM to interpret it, and produces a structured `ResearchPlan` that tells downstream agents exactly what to fetch and analyze.

## Acceptance Criteria
- [x] `backend/app/agents/coordinator.py` — `coordinator_node(state: AgentState) → AgentState`
- [x] LLM system prompt: "You are a Singapore policy data research coordinator. Interpret the query and produce a JSON research plan."
- [x] LLM called with `json_mode=True` → response parsed to `ResearchPlan`
- [x] `ResearchPlan` fields populated: `sources` (list from: singstat/datagov/mock), `topics` (list of strings), `date_range` (tuple), `sub_tasks` (list of fetch instructions)
- [x] If LLM parse fails: use rule-based fallback (extract years from query, default sources to all)
- [x] Emits `THINK` step (reasoning) + `DONE` step (plan) to WebSocket via `publish_step()`
- [x] Both steps also written to `AgentLog` via `crud.create_agent_log()`
- [x] `state["current_agent"]` updated to `"coordinator"` on entry
- [x] `state["research_plan"]` populated before returning

## Technical Notes
- Coordinator has NO tools — it's a pure LLM call
- Use temperature=0.3 for deterministic planning
- `sub_tasks` example: `["Fetch employment by industry 2020-2024 from SingStat", "Fetch ICT sector headcount from Data.gov.sg"]`
