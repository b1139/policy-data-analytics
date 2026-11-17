# S19 — Data Quality & Validation Pipeline
**Epic**: E4 Data | **Priority**: P1 | **Assigned**: data-dev  
**Depends on**: S17, S18

## Description
Build a data quality validation pipeline that checks incoming DataFrames for common issues and produces a structured quality report. All fetched data passes through this before reaching the analytics engine.

## Acceptance Criteria
- [ ] `backend/app/services/data_service.py` — `DataQualityValidator` class
- [ ] `validate(df: pd.DataFrame) → ValidationResult` with checks:
  - **Null check**: flag columns with >10% null values
  - **Type consistency**: flag columns that appear numeric but have string values
  - **Date range sanity**: if date column present, verify min/max are within expected range (1990–2030)
  - **Outlier detection**: flag numeric columns where any value > 3 IQR from median
  - **Empty DataFrame**: return failed result immediately
- [ ] `ValidationResult` Pydantic model: `{passed: bool, warnings: list[str], errors: list[str], stats: dict}`
- [ ] `stats` includes: `{row_count, col_count, null_pct_by_col, dtypes}`
- [ ] `DataService` class:
  - `fetch_and_validate(source_id, dataset_id) → (df, ValidationResult)`
  - `cache_dataset(df, source, source_id, metadata) → Dataset` — hash-based dedup
- [ ] Data quality warnings added to analysis result `metadata.data_quality_issues`
- [ ] Data is NEVER silently dropped — only flagged with warnings

## Technical Notes
- Hash: `hashlib.sha256(df.to_json().encode()).hexdigest()`
- Validation doesn't raise — always returns a result even for bad data
