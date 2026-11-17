# S22 — Plotly Visualization Service
**Epic**: E5 Analytics | **Priority**: P1 | **Assigned**: analytics-dev  
**Depends on**: S20

## Description
Build the `VisualizationService` that generates Plotly chart specifications from DataFrames. Charts are returned as JSON dicts (not rendered images) so the frontend can render them interactively.

## Acceptance Criteria
- [ ] `backend/app/services/visualization_service.py` — `VisualizationService` class
- [ ] `line_chart(df, x_col, y_col, title, source_label, color=None) → dict`
  - Plotly line chart with markers
  - Source annotation bottom-right
  - SG government blue (#0F5FA6) as default color
- [ ] `bar_chart(df, x_col, y_col, title, source_label, orientation="v") → dict`
  - Clustered bar chart
  - Amber (#F4A201) as default color
- [ ] `multi_line_chart(df, x_col, y_cols, title, source_label) → dict`
  - Multiple series line chart for sector comparisons
- [ ] All charts: `fig.update_layout(template="plotly_white", ...)` for clean look
- [ ] All charts: axis titles, chart title, hover tooltips
- [ ] Returns `fig.to_json()` parsed to dict (not raw string)
- [ ] `generate_chart` LangChain tool wrapper in `analysis_tools.py` calls this service

## Technical Notes
- Do NOT call `fig.show()` — server-side only, no rendering
- Chart JSON must be serializable as part of PostgreSQL JSONB result
- Handle edge case: empty DataFrame → return `{error: "no_data", type: "empty_chart"}`
