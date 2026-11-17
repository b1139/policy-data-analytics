# S15 — Multi-Agent Orchestration & ReAct
**Epic**: E3 Agents | **Priority**: P0 | **Assigned**: agent-dev  
**Depends on**: S12, S13, S14

## Description
Wire the full LangGraph graph: connect coordinator → extraction → analytics → END with proper conditional edges, integrate the graph with the FastAPI background task, and perform end-to-end smoke test.

## Acceptance Criteria
- [ ] `graph.py` `build_graph()` connects all three nodes in correct order
- [ ] Conditional edge from `extraction`:
  - If `len(state["extraction_errors"]) > 0` and `len(state["raw_datasets"]) == 0` → END with FAILED
  - Otherwise → `analytics`
- [ ] `run_analysis()` calls `crud.update_analysis_status(RUNNING)` before graph start
- [ ] On graph completion: calls `crud.update_analysis_status(DONE, result=assembled_result)`
- [ ] On unhandled exception: calls `crud.update_analysis_status(FAILED, error_msg=str(e))`
- [ ] `AnalysisResult` assembled from final state: `{insights, charts, citations, stats_summary}`
- [ ] FastAPI `POST /api/v1/analysis/start` wires `BackgroundTasks.add_task(run_analysis, ...)`
- [ ] Integration smoke test: `USE_MOCK_DATA_SOURCES=true` + `MOCK_LLM=true` → full graph runs, Analysis marked DONE
- [ ] WebSocket receives: at least 5 step messages + 1 ANALYSIS_DONE message during smoke test

## Technical Notes
- `run_analysis` is the entry point from FastAPI background task
- Use `graph.ainvoke(initial_state)` for async execution
- Assembled citations: extracted from `state["raw_datasets"]` metadata
