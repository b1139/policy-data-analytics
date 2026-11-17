# S28 — Analysis History & Export
**Epic**: E6 Frontend | **Priority**: P2 | **Assigned**: frontend-dev  
**Depends on**: S27

## Description
Build the analysis history page showing all past analyses with status, quick actions (re-run, delete, export), and the export functionality for downloading analysis results.

## Acceptance Criteria
- [ ] `frontend/app/dashboard/history/page.tsx` — history page
- [ ] `frontend/components/history/HistoryList.tsx`
  - Calls `GET /api/v1/analysis/?skip=0&limit=20`
  - Infinite scroll or pagination (load more button)
  - Each row: query preview (truncated), status badge, created_at, action buttons
  - Status badges: RUNNING=yellow animated, DONE=green, FAILED=red, PENDING=gray
  - Click row → navigates to `/dashboard/analysis/{id}`
- [ ] `frontend/components/history/AnalysisCard.tsx` — individual card
  - Action buttons: "Open", "Export JSON", "Delete"
  - Delete: confirmation `AlertDialog` before API call
  - Export: triggers download of `analysis_{id}.json`
- [ ] Empty state: "No analyses yet" with CTA to run first query
- [ ] `useAnalysis` hook: wraps TanStack Query for history + detail + delete operations
- [ ] History in sidebar navigation link with count badge

## Technical Notes
- Download via `URL.createObjectURL(blob)` + hidden anchor click
- Delete optimistically removes from list; re-fetches on error
- TanStack Query `invalidateQueries` after delete
