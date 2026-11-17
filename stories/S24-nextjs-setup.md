# S24 — Next.js App Setup & Layout
**Epic**: E6 Frontend | **Priority**: P0 | **Assigned**: frontend-dev  
**Depends on**: S01

## Description
Bootstrap the Next.js frontend application: root layout, global providers, type definitions, API client, and routing structure. This is the shell that all UI components live inside.

## Acceptance Criteria
- [ ] `frontend/app/layout.tsx` — root layout with `QueryClientProvider` + `Toaster`
- [ ] `frontend/app/page.tsx` — redirects to `/dashboard`
- [ ] `frontend/app/dashboard/layout.tsx` — sidebar navigation + main content area
- [ ] `frontend/app/dashboard/page.tsx` — query input + recent analyses
- [ ] `frontend/app/dashboard/analysis/[id]/page.tsx` — analysis detail page (shell)
- [ ] `frontend/types/index.ts` — TypeScript interfaces:
  - `Analysis`, `AnalysisListItem`, `AnalysisStatus`
  - `AgentStep`, `AgentName`, `StepType`
  - `ChartSpec`, `Citation`, `StatsResult`
- [ ] `frontend/lib/api.ts` — Axios instance + typed functions:
  - `startAnalysis(query: string) → Promise<{analysis_id, ws_url}>`
  - `getAnalysis(id: string) → Promise<Analysis>`
  - `listAnalyses(skip?, limit?) → Promise<{items, total}>`
  - `exportAnalysis(id: string) → Promise<Blob>`
  - `deleteAnalysis(id: string) → Promise<void>`
- [ ] `frontend/lib/utils.ts` — `cn()`, `formatDate()`, `formatStatus()`
- [ ] `next.config.ts` — API proxy: `/api/*` rewrites to `http://backend:8000/api/*`
- [ ] `tailwind.config.ts` — includes SG gov colors: `sg-blue: #0F5FA6`, `sg-amber: #F4A201`

## Technical Notes
- Use `"use client"` only on components that need interactivity
- API client uses `NEXT_PUBLIC_API_URL` from env
- Sidebar: links to Dashboard, History
