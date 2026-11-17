# S23 — Report Generation with Citations
**Epic**: E5 Analytics | **Priority**: P1 | **Assigned**: analytics-dev  
**Depends on**: S21, S22

## Description
Implement the `ReportBuilder` that assembles the final `AnalysisResult` from all analytics outputs. This is the definitive output format saved to the database and sent to the frontend.

## Acceptance Criteria
- [ ] `backend/app/services/analysis_service.py` — `ReportBuilder` class
- [ ] `build(insights, charts, stats, datasets) → AnalysisResult` Pydantic model
- [ ] `AnalysisResult` fields:
  - `insights: str` — LLM narrative
  - `charts: list[ChartSpec]` — Plotly JSON dicts
  - `citations: list[Citation]` — data source credits
  - `stats_summary: dict` — key numbers for metrics cards
  - `generated_at: datetime`
  - `truncated_preview: str` — first 200 chars of insights
- [ ] `Citation` model: `{source: str, title: str, url: str | None, accessed: datetime, dataset_id: str}`
- [ ] `stats_summary` populated with: `trend_direction`, `peak_year`, `overall_change_pct`, `data_points_count`
- [ ] Citations extracted automatically from `state["raw_datasets"]` metadata
- [ ] `AnalysisResult` serializable to JSON (for JSONB storage and export endpoint)
- [ ] Final report stored in `analyses.result` JSONB column via `update_analysis_status()`

## Technical Notes
- Use `model.model_dump(mode="json")` for JSON serialization
- If no citations could be extracted: include `{source: "Data not available", ...}` placeholder
