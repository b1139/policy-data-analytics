# S13 — Data Extraction Agent
**Epic**: E3 Agents | **Priority**: P0 | **Assigned**: agent-dev  
**Depends on**: S11, S17

## Description
Implement the Data Extraction agent node using LangGraph's ReAct pattern. It reads the `ResearchPlan`, uses tools to fetch datasets from registered data sources, normalizes them to DataFrames, and stores results in the agent state.

## Acceptance Criteria
- [x] `backend/app/agents/extraction.py` — `extraction_node(state: AgentState) → AgentState`
- [x] Uses `create_react_agent` with 3 tools from `data_tools.py`:
  - `list_available_datasets(source, keywords)` — calls `DataSourceRegistry.get(source).search()`
  - `fetch_dataset(source, dataset_id)` — calls `DataSourceRegistry.get(source).fetch()`
  - `validate_dataframe(df_json)` — calls `DataQualityValidator.validate()`
- [x] Multi-source extraction: extracts from BOTH `singstat` (Table Builder / MCP) AND `datagov` (Data.gov.sg v2/v1) concurrently
- [x] Dynamic discovery on Data.gov.sg via `api-production.data.gov.sg` when dataset ID is resolved by keywords
- [x] Iterates through `state["research_plan"]["planned_datasets"]` and `sub_tasks`
- [x] Populates `state["raw_datasets"]` and `state["selected_datasets"]` lists with `{source, dataset_id, title, df_json, metadata, dq_report}`
- [x] On partial failures: adds to `state["extraction_errors"]`, continues with available data and resilient fallback
- [x] Emits `ACT` step per tool call + `OBSERVE` step per tool result to WebSocket
- [x] Maximum 15 ReAct iterations (prevents infinite loops)
- [x] `state["current_agent"]` updated to `"extraction"` on entry

## Technical Notes
- `df_json` = `df.to_json(orient="split")` for compact representation
- `fetch_dataset` tool uses `DataSourceRegistry` (from data-dev's S16)
- ReAct agent stops when all sub_tasks have been attempted (success or failure)
- Data.gov.sg connector supports modern `api-production.data.gov.sg` search and `api-open.data.gov.sg` initiate-download pipeline with CKAN backwards compatibility
