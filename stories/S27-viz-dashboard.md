# S27 — Interactive Visualization Dashboard
**Epic**: E6 Frontend | **Priority**: P1 | **Assigned**: frontend-dev  
**Depends on**: S26, S22

## Description
Build the analysis results dashboard: insight text panel, metric stats cards, interactive Plotly charts, and citations panel. All components are populated from the final `AnalysisResult` JSON.

## Acceptance Criteria
- [ ] `frontend/components/dashboard/InsightPanel.tsx`
  - Renders insight text with paragraphs preserved
  - Citation links inline (source name as clickable link)
  - "Copy insight" button
- [ ] `frontend/components/dashboard/StatsCards.tsx`
  - 4 metric cards from `stats_summary`: Trend Direction, Peak Year, Overall Change %, Data Points
  - Cards use color: green=positive trend, red=negative, gray=stable
- [ ] `frontend/components/charts/ChartRenderer.tsx`
  - Accepts Plotly JSON spec (`ChartSpec`) → renders using Plotly.js via dynamic import
  - Loading skeleton while Plotly loads
  - Fallback: data table if Plotly fails to render
  - Download chart button (PNG export via `Plotly.downloadImage`)
- [ ] `frontend/components/dashboard/CitationsPanel.tsx`
  - Expandable list of data sources
  - Source name, dataset title, accessed date
  - External link icon for URLs
- [ ] Full analysis page: 2-column layout (AgentMonitor left, Results right on desktop)
- [ ] Results panel shows skeleton loaders until ANALYSIS_DONE received

## Technical Notes
- Load Plotly.js dynamically: `import("plotly.js-dist")` to avoid SSR issues
- Plotly JSON → `Plotly.newPlot(divRef, fig.data, fig.layout)`
- Use `react-plotly.js` package OR manual DOM approach
