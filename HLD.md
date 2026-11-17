# 🏗️ High Level Design (HLD)
## Agentic Policy Data Analytics Platform

---

## 1. System Context

```
                        ┌─────────────────────────────────────────────────────┐
                        │           Policy Analytics Platform                  │
                        │                                                       │
 Policy Analyst ───────▶│  Next.js Web App  ◀──WebSocket──▶  FastAPI Backend   │
                        │       (UI)                            (Orchestrator)  │
                        │                                             │          │
                        │                                    LangGraph Engine   │
                        │                                    ┌────────────────┐ │
                        │                                    │ Coordinator    │ │
                        │                                    │ Extraction     │ │
                        │                                    │ Analytics      │ │
                        │                                    └───────┬────────┘ │
                        └──────────────────────────────────────────-│───────────┘
                                                                     │
              ┌──────────────────────────────────────────────────────┤
              │                        External                      │
              ▼                                                       ▼
   ┌─────────────────────┐                                 ┌──────────────────────┐
   │  Government Sources │                                 │    LLM Providers     │
   │  • SingStat MCP/API │                                 │  • Google Gemini 1.5 │
   │  • Data.gov.sg v2   │                                 │  • AWS Bedrock Claude│
   │  • MOM / ACRA Stats │                                 │  • OpenAI / Anthropic│
   │  • Mock Internal DB │                                 │  • Offline Mock LLM  │
   └─────────────────────┘                                 └──────────────────────┘
```

---

## 2. Component Architecture

### 2.1 Frontend (Next.js 14 + TypeScript)
- **Query Interface**: Natural-language input box → submits to backend
- **Agent Monitor**: WebSocket-driven live feed of agent reasoning steps
- **Dashboard**: Recharts-powered interactive charts and tables
- **History**: Paginated list of past analyses with export (JSON/PDF/CSV)

### 2.2 Backend (FastAPI + Python 3.15)
- **API Layer**: RESTful endpoints + WebSocket channel
- **Task Runner**: `asyncio` background tasks (no Celery required at MVP)
- **LangGraph Engine**: State machine that orchestrates 3 agents
- **Service Layer**: AnalysisService, DataService, VisualizationService

### 2.3 Agent System (LangGraph)
| Agent | Responsibility |
|-------|---------------|
| **Data Coordinator** | Interprets user query, creates research plan, delegates sub-tasks |
| **Data Extraction** | Fetches raw data from gov APIs and mock sources; normalizes formats |
| **Analytics** | Runs stats, invokes LLM for insights, generates Plotly charts |

### 2.4 Data Layer
- **PostgreSQL**: Analysis records, datasets, agent logs, cached results
- **Redis**: Session caching, WebSocket pub/sub for live updates
- **In-memory**: Pandas DataFrames during analysis pipeline

### 2.5 LLM Integration
- **Provider Abstraction**: Uniform interface over OpenAI + Anthropic
- **Routing**: Primary = OpenAI GPT-4o; Fallback = Anthropic Claude 3.5 Sonnet
- **Use cases**: Query interpretation, insight narration, report generation

---

## 3. Data Flow — End to End

```
1. User types: "Analyse employment trends in tech sector 2020-2024"
         │
         ▼
2. Frontend POST /api/v1/analysis/start
         │
         ▼
3. Backend creates Analysis record (status=RUNNING) → returns {analysis_id, ws_url}
         │
         ▼
4. Background task spins up LangGraph graph with query as input
         │
         ▼
5. Data Coordinator Agent
   • LLM: interprets query → creates research plan JSON
   • Identifies: sources=[singstat, datagov], years=[2020..2024], topic=employment/tech
         │
         ▼
6. Data Extraction Agent
   • Fetches SingStat employment tables (CSV/JSON)
   • Fetches Data.gov.sg sector datasets
   • Validates, cleans, merges → Pandas DataFrame
         │
         ▼
7. Analytics Agent
   • Computes: YoY growth, sector share, trend regression
   • LLM: generates narrative insights from stats dict
   • Plotly: creates line chart + bar chart JSON specs
         │
         ▼
8. Report assembled: {insights, charts, citations, raw_data_ref}
         │
         ▼
9. Result saved to PostgreSQL; WebSocket pushes each step + final result
         │
         ▼
10. Frontend renders charts, insight text, source citations
```

---

## 4. API Design (High Level)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analysis/start` | Submit a natural-language query |
| GET | `/api/v1/analysis/{id}` | Poll analysis status & results |
| GET | `/api/v1/analysis/` | List past analyses (paginated) |
| GET | `/api/v1/analysis/{id}/export` | Download report (JSON/PDF) |
| DELETE | `/api/v1/analysis/{id}` | Delete an analysis |
| GET | `/api/v1/health` | Health check (LLM + DB status) |
| WS | `/ws/analysis/{id}` | Real-time agent step streaming |

---

## 5. Deployment Architecture

```
docker compose up
  ├── frontend   (Next.js → port 3000)
  ├── backend    (FastAPI → port 8000)
  ├── postgres   (PostgreSQL → port 5432)
  └── redis      (Redis → port 6379)

Reverse proxy: nginx (port 80/443) → routes /api/* → backend, /* → frontend
```

---

## 6. Security & Config
- API keys stored in `.env` (never in code)
- Pydantic Settings reads env vars with strict validation
- CORS restricted to known origins
- No external auth required at MVP (demo/assessment context)
