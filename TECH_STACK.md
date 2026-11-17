# 🛠️ Tech Stack
## Agentic Policy Data Analytics Platform

---

## Stack Choices Summary

| Layer | Technology | Version | Why |
|-------|-----------|---------|-----|
| **Frontend Framework** | Next.js (App Router) | 14.x | SSR, file-based routing, React Server Components, Vercel-ready |
| **Frontend Language** | TypeScript | 5.x | Type safety, better IDE support |
| **UI Components** | shadcn/ui + Tailwind CSS | latest | Copy-paste components, zero runtime CSS-in-JS |
| **Charts (frontend)** | Recharts | 2.x | Declarative React charts; renders Plotly specs via JSON |
| **Real-time (frontend)** | native WebSocket | — | No library needed; browser-native |
| **Data fetching** | TanStack Query (React Query) | v5 | Caching, refetch, background sync |
| **Backend Framework** | FastAPI | 0.111+ | Async-native, Pydantic v2, auto OpenAPI docs |
| **Backend Language** | Python | 3.15+ | Walrus operator, structural matching, lazy imports, frozendict, JIT, high performance |
| **ORM** | SQLAlchemy (async) | 2.0 | Async sessions, modern mapped_column API |
| **DB Migrations** | Alembic | 1.13 | SQLAlchemy-native, revision history |
| **Validation** | Pydantic v2 | 2.x | 5–50x faster than v1, Rust core |
| **Database** | PostgreSQL | 15 | JSONB, async driver (asyncpg), reliable |
| **Cache / Pub-Sub** | Redis | 7.x | WebSocket pub/sub, session cache |
| **Agentic Framework** | LangGraph | 0.1+ | Graph-based state machine; first-class ReAct; debuggable |
| **LLM SDK** | LangChain Core | 0.2+ | Provider adapters, message types |
| **LLM Provider 1** | OpenAI GPT-4o | latest | Best reasoning quality; well-documented |
| **LLM Provider 2** | Anthropic Claude 3.5 Sonnet | latest | Strong structured output; reliable fallback |
| **Data Processing** | Pandas + NumPy | 2.x / 1.x | Industry standard; great for tabular gov data |
| **HTTP Client** | httpx | 0.27 | Async-native, used by FastAPI internally |
| **Testing (backend)** | pytest + pytest-asyncio | 8.x | Async test support; fixture ecosystem |
| **Testing (frontend)** | Jest + Testing Library | 29.x | Standard React testing |
| **Containerization** | Docker + Docker Compose | v2 | Reproducible envs; single command startup |
| **CI/CD** | GitHub Actions | — | Native to GitHub; free for public repos |
| **Linting/Formatting** | Ruff (Python) + ESLint/Prettier | — | Fast; single tool replaces flake8+isort+black |

---

## Justifications for Key Choices

### LangGraph over CrewAI / AutoGen
- **Deterministic graph** → easier to debug than emergent multi-agent chats
- **State is explicit** → every agent reads/writes a typed `AgentState` TypedDict
- **Built-in ReAct** → `create_react_agent` helper ships out of the box
- **Tool calling** → first-class LangChain tool integration

### FastAPI over Flask / Django
- **Async native** → non-blocking I/O critical for concurrent LLM + data fetches
- **Pydantic v2 built-in** → request/response validation with zero boilerplate
- **Auto OpenAPI** → free interactive docs at `/docs`

### PostgreSQL over MongoDB / SQLite
- **JSONB** → flexible result storage without schema rigidity
- **Relational** → analysis ↔ dataset joins stay clean
- **asyncpg** → fastest Python PostgreSQL driver

### OpenAI + Anthropic over Bedrock
- **Direct APIs** → simpler setup (no AWS IAM/credentials complexity)
- **Both have Python SDKs** → easy to wrap in an abstraction
- **Fast to swap** → abstraction layer means provider can change without logic change
- Bedrock can be added as a third provider in a future story

---

## Python Requirements

```txt
# requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.4
pydantic-settings==2.3.3
sqlalchemy[asyncio]==2.0.30
alembic==1.13.1
asyncpg==0.29.0
redis[hiredis]==5.0.6
langchain-core==0.2.10
langchain-openai==0.1.14
langchain-anthropic==0.1.17
langgraph==0.1.14
pandas==2.2.2
numpy==1.26.4
httpx==0.27.0
plotly==5.22.0
scipy==1.13.1
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
ruff==0.4.9
```

## Node Requirements

```json
{
  "dependencies": {
    "next": "14.2.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "typescript": "^5.5.2",
    "@tanstack/react-query": "^5.45.1",
    "recharts": "^2.12.7",
    "tailwindcss": "^3.4.4",
    "shadcn-ui": "^0.8.0",
    "axios": "^1.7.2",
    "lucide-react": "^0.395.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "jest": "^29.7.0",
    "eslint": "^8.57.0"
  }
}
```
