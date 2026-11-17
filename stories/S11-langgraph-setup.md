# S11 — LangGraph Setup & State Definitions
**Epic**: E3 Agents | **Priority**: P0 | **Assigned**: agent-dev  
**Depends on**: S08, S09

## Description
Initialize the LangGraph framework, define the shared `AgentState` TypedDict, and set up the graph skeleton (nodes registered, edges declared). This is the scaffolding that S12–S15 fill in.

## Acceptance Criteria
- [ ] `backend/app/agents/state.py` — `AgentState` TypedDict matching LLD.md §3 exactly
- [ ] `backend/app/agents/state.py` — `ResearchPlan` TypedDict
- [ ] `backend/app/agents/graph.py` — `build_graph()` function:
  - Creates `StateGraph(AgentState)`
  - Adds nodes: `coordinator`, `extraction`, `analytics`
  - Adds edges per LLD.md §4 flow diagram
  - Returns compiled graph with `checkpointer=None` (stateless for now)
- [ ] `graph.py` — `run_analysis(analysis_id: str, query: str) → AnalysisResult` async function
  - Instantiates the graph, runs with initial state `{query, analysis_id}`
  - Returns final state's assembled result
- [ ] `backend/app/agents/__init__.py` exports `build_graph`, `run_analysis`
- [ ] `backend/app/agents/tools/__init__.py` exists (empty, populated by S13/S14)
- [ ] Smoke test: graph with stub nodes (just return state unchanged) compiles and runs

## Technical Notes
- Use `langgraph.graph.StateGraph`
- Conditional edge from extraction: if `len(state["extraction_errors"]) > 2` → END, else → analytics
- `run_analysis` is called by the FastAPI background task from S07
