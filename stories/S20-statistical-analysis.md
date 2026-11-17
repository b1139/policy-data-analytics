# S20 — Statistical Analysis Engine
**Epic**: E5 Analytics | **Priority**: P0 | **Assigned**: analytics-dev  
**Depends on**: S19

## Description
Implement the statistical analysis engine that computes policy-relevant statistics from DataFrames: trend analysis, summary stats, sector shares, and correlations. All computations must be deterministic and return typed results.

## Acceptance Criteria
- [ ] `backend/app/services/analysis_service.py` — `StatisticsEngine` class
- [ ] `compute_trend(df, value_col, time_col) → TrendResult`:
  - Linear regression (scipy linregress) → `{slope, intercept, r2, p_value}`
  - YoY growth rates → `{year: pct_change}` dict
  - `overall_trend`: `"increasing"/"decreasing"/"stable"` (based on slope sign + p_value < 0.05)
- [ ] `compute_summary_stats(df, value_col) → SummaryResult`:
  - `{mean, median, std, min, max, count, latest_value, earliest_value}`
- [ ] `compute_sector_share(df, sector_col, value_col, year) → SectorShareResult`:
  - `{sector: percentage}` dict for pie chart data
- [ ] `compute_correlation(df, col_a, col_b) → CorrelationResult`:
  - `{pearson_r, spearman_r, p_value, interpretation}`
- [ ] `StatsResult` Pydantic model aggregates all outputs
- [ ] All computations handle NaN values (dropna before calculations)

## Technical Notes
- `scipy.stats.linregress` for trend
- `scipy.stats.pearsonr` and `spearmanr` for correlation
- If <3 data points: return `{error: "insufficient_data"}` instead of crashing
