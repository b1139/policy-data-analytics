# S14 — Analytics Agent
**Epic**: E3 Agents | **Priority**: P0 | **Assigned**: agent-dev  
**Depends on**: S11, S20

## Description
Implement the Analytics agent node. It takes the extracted datasets and runs statistical analysis, generates LLM-powered insights, and creates chart specifications. This is the intelligence layer.

## Acceptance Criteria
- [ ] `backend/app/agents/analytics.py` — `analytics_node(state: AgentState) → AgentState`
- [ ] Uses `create_react_agent` with 3 tools from `analysis_tools.py` + `llm_tools.py`:
  - `compute_statistics(df_json, analysis_type)` — calls `StatisticsEngine`
  - `generate_chart(df_json, chart_type, title)` — calls `VisualizationService`
  - `generate_insight(stats_dict, query, sources)` — calls LLM for narrative
- [ ] `state["stats"]` populated with `StatisticsEngine` output
- [ ] `state["insights"]` populated with LLM narrative text
- [ ] `state["charts"]` populated with list of Plotly JSON dict specs
- [ ] Minimum 1 chart generated per analysis (line chart of main trend)
- [ ] Emits ACT/OBSERVE steps to WebSocket per tool call
- [ ] `state["current_agent"]` updated to `"analytics"` on entry
- [ ] If no raw_datasets in state (all extraction failed): emits DONE with partial result

## Technical Notes
- `generate_insight` tool wraps the `InsightGenerator` service from S21
- Charts: at minimum generate trend chart; optionally sector comparison chart
- `analysis_type` for `compute_statistics`: `"trend"`, `"summary"`, `"sector_share"`, `"correlation"`
