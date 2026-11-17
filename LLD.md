# 🔩 Low Level Design (LLD)
## Agentic Policy Data Analytics Platform

---

## 1. Database Schema

```sql
-- Analyses (top-level record per user query)
CREATE TABLE analyses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query       TEXT NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                -- PENDING | RUNNING | DONE | FAILED
    result      JSONB,          -- final {insights, charts, citations}
    metadata    JSONB,          -- research_plan, sources_used, duration_ms
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Execution Logs (one row per agent step)
CREATE TABLE agent_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    agent_name  VARCHAR(50) NOT NULL,   -- coordinator | extraction | analytics
    step_type   VARCHAR(30) NOT NULL,   -- THINK | ACT | OBSERVE | DONE | ERROR
    content     JSONB NOT NULL,         -- step detail (reasoning, tool call, result)
    sequence_no INTEGER NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_agent_logs_analysis ON agent_logs(analysis_id, sequence_no);

-- Datasets (fetched & cached external data)
CREATE TABLE datasets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      VARCHAR(50) NOT NULL,   -- singstat | datagov | mom | mock_internal
    source_id   VARCHAR(255),           -- external dataset id/url
    title       TEXT,
    data_hash   VARCHAR(64),            -- SHA-256 for dedup
    row_count   INTEGER,
    columns     JSONB,                  -- [{name, dtype, sample_values[]}]
    fetched_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ             -- TTL for cache invalidation
);

-- Analysis ↔ Dataset mapping (many-to-many)
CREATE TABLE analysis_datasets (
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    dataset_id  UUID REFERENCES datasets(id),
    PRIMARY KEY (analysis_id, dataset_id)
);
```

---

## 2. Project Directory Structure

```
policy-analytics-platform/
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                    ← redirect to /dashboard
│   │   └── dashboard/
│   │       ├── page.tsx
│   │       └── analysis/[id]/page.tsx
│   ├── components/
│   │   ├── query/QueryInput.tsx
│   │   ├── agents/AgentMonitor.tsx
│   │   ├── charts/ChartRenderer.tsx
│   │   ├── history/HistoryList.tsx
│   │   └── ui/                         ← shadcn/ui components
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   └── useAnalysis.ts
│   ├── lib/
│   │   ├── api.ts                      ← typed API client
│   │   └── utils.ts
│   ├── types/index.ts
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── main.py                     ← FastAPI app factory
│   │   ├── core/
│   │   │   ├── config.py               ← Pydantic Settings
│   │   │   ├── database.py             ← SQLAlchemy async engine
│   │   │   └── redis.py
│   │   ├── models/
│   │   │   ├── analysis.py             ← SQLAlchemy ORM models
│   │   │   ├── agent_log.py
│   │   │   └── dataset.py
│   │   ├── schemas/
│   │   │   ├── analysis.py             ← Pydantic request/response
│   │   │   └── agent.py
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── analysis.py         ← REST routes
│   │   │   │   └── health.py
│   │   │   └── websocket.py            ← WS endpoint
│   │   ├── agents/
│   │   │   ├── state.py                ← LangGraph GraphState TypedDict
│   │   │   ├── coordinator.py          ← Coordinator agent node
│   │   │   ├── extraction.py           ← Extraction agent node
│   │   │   ├── analytics.py            ← Analytics agent node
│   │   │   ├── graph.py                ← Compile & run LangGraph graph
│   │   │   └── tools/
│   │   │       ├── data_tools.py       ← fetch_dataset, list_sources tools
│   │   │       ├── analysis_tools.py   ← compute_stats, generate_chart tools
│   │   │       └── llm_tools.py        ← generate_insight, interpret_query
│   │   ├── llm/
│   │   │   ├── base.py                 ← AbstractLLMProvider
│   │   │   ├── openai_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   └── router.py               ← Primary + fallback routing
│   │   ├── data_sources/
│   │   │   ├── base.py                 ← AbstractDataSource
│   │   │   ├── singstat.py
│   │   │   ├── datagov.py
│   │   │   └── mock_internal.py
│   │   └── services/
│   │       ├── analysis_service.py     ← orchestrate full pipeline
│   │       ├── data_service.py         ← dataset CRUD + cache
│   │       └── visualization_service.py ← Plotly chart builder
│   ├── alembic/                        ← DB migrations
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── llm/
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml
├── docker-compose.test.yml
├── nginx.conf
├── .env.example
├── .github/workflows/
│   ├── test.yml
│   └── deploy.yml
├── README.md
├── ARCHITECTURE.md
├── TESTING.md
└── DATA_SOURCES.md
```

---

## 3. LangGraph Agent State

```python
# app/agents/state.py
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

class ResearchPlan(TypedDict):
    sources: List[str]
    topics: List[str]
    date_range: tuple[str, str]
    sub_tasks: List[str]

class AgentState(TypedDict):
    # Inputs
    query: str
    analysis_id: str

    # Coordinator outputs
    research_plan: ResearchPlan

    # Extraction outputs
    raw_datasets: List[dict]        # [{source, title, dataframe_json, metadata}]
    extraction_errors: List[str]

    # Analytics outputs
    stats: dict                     # computed statistics dict
    insights: str                   # LLM-generated narrative
    charts: List[dict]              # Plotly figure JSON specs

    # Control
    messages: Annotated[list, add_messages]
    current_agent: str
    errors: List[str]
    step_count: int
```

---

## 4. LangGraph Graph Flow

```
              ┌─────────────┐
   START ────▶│ coordinator │
              └──────┬──────┘
                     │ research_plan
                     ▼
              ┌─────────────┐
              │  extraction │◀── retry if extraction_errors
              └──────┬──────┘
                     │ raw_datasets
                     ▼
              ┌─────────────┐
              │  analytics  │
              └──────┬──────┘
                     │ stats + insights + charts
                     ▼
                    END

Conditional edges:
- extraction → coordinator  (if critical failure, re-plan)
- analytics  → END          (always, errors captured in state)
```

---

## 5. LLM Provider Interface

```python
# app/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict          # {input_tokens, output_tokens}
    latency_ms: float

class AbstractLLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
```

---

## 6. Data Source Interface

```python
# app/data_sources/base.py
from abc import ABC, abstractmethod
import pandas as pd

class AbstractDataSource(ABC):
    source_id: str
    display_name: str
    
    @abstractmethod
    async def search(self, keywords: list[str], **filters) -> list[dict]: ...
    # Returns: [{id, title, description, url, format}]

    @abstractmethod
    async def fetch(self, dataset_id: str) -> pd.DataFrame: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
```

---

## 7. WebSocket Message Protocol

```jsonc
// Server → Client (streamed during analysis)
{
  "type": "AGENT_STEP",        // or ANALYSIS_DONE | ANALYSIS_ERROR
  "analysis_id": "uuid",
  "agent": "coordinator",       // coordinator | extraction | analytics
  "step_type": "THINK",         // THINK | ACT | OBSERVE | DONE | ERROR
  "sequence_no": 3,
  "content": {
    "reasoning": "I need to fetch employment data from SingStat...",
    "tool_call": null           // populated on ACT steps
  },
  "timestamp": "2025-01-15T10:00:00Z"
}

// Final result
{
  "type": "ANALYSIS_DONE",
  "analysis_id": "uuid",
  "result": {
    "insights": "Employment in the technology sector grew 18%...",
    "charts": [{ /* Plotly figure JSON */ }],
    "citations": [{ "source": "SingStat", "url": "...", "accessed": "..." }],
    "stats_summary": { "trend": "+18%", "peak_year": 2023 }
  }
}
```

---

## 8. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Agent framework | LangGraph | Deterministic state machine; easy to debug; ReAct native |
| Task async | asyncio background tasks | No Celery overhead at MVP scale |
| DB | PostgreSQL async (asyncpg) | JSONB for flexible result storage; async for perf |
| Cache/WS | Redis pub/sub | Decouple WS from HTTP; horizontal scaling ready |
| LLM routing | Simple try/except fallback | Pragmatic; avoids complex circuit breaker at MVP |
| Charts | Plotly (backend) + JSON spec to frontend | No chart library version mismatch; spec is portable |
| Frontend state | React Query + Context | Simple; avoids Redux overhead |
