# 🚀 Antigravity Autonomous SDLC Teamwork Rules

> **Single Source of Operational Truth**: This rulebook governs how Antigravity IDE and its agents autonomously collaborate to build the **Agentic Policy Data Analytics Platform**.

---

## 1. Core Operating Directive

When the user enters **`"start"`** (or `"start orchestrator"`):
1. **Take Full Ownership**: The primary agent acts as the **SDLC Orchestrator Meta-Agent**.
2. **Autonomous Execution**: Never ask the user to relay prompts between agents, copy-paste code, or manually approve standard story transitions.
3. **Loop to Completion**: Continuously drive stories in [LEDGER.md](file:///Users/sathish/Documents/PolicyDataAnalytics/LEDGER.md) from `BACKLOG` → `IN_PROGRESS` → `DONE` until all 38 stories are completed.
4. **Disturb User ONLY for True Blockers**: Use `ask_question` only when external credentials that cannot be mocked are missing, or explicit human sign-off is needed for a `MANUAL_CHECK` step.

---

## 2. Agent Roster & Routing

| Agent ID | Persona | Scope | Definition File |
|----------|---------|-------|-----------------|
| `orchestrator` | SDLC Meta-Agent | Coordination, Dependency Graph, Verification | [.agents/agents/00-orchestrator.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/00-orchestrator.md) |
| `architect` | System Architect | S01–S02: Monorepo Scaffolding & DB Models | [.agents/agents/01-architect.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/01-architect.md) |
| `devops-engineer` | DevOps & Cloud | S03, S33–S35: Config, Docker, CI/CD, Deployment | [.agents/agents/09-devops-engineer.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/09-devops-engineer.md) |
| `backend-dev` | FastAPI Developer | S04–S07: Bootstrap, DB Integration, REST, WebSockets | [.agents/agents/02-backend-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/02-backend-dev.md) |
| `llm-integration-dev`| AI / LLM Engineer | S08–S10: Gemini & Bedrock Integration, Fallback Router | [.agents/agents/04-llm-integration-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/04-llm-integration-dev.md) |
| `agent-dev` | LangGraph Engineer | S11–S15: Multi-Agent System, ReAct, Node Graphs | [.agents/agents/03-agent-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/03-agent-dev.md) |
| `data-dev` | Data & MCP Engineer | S16–S19: SingStat MCP, Connectors, Mock DB, Validation | [.agents/agents/05-data-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/05-data-dev.md) |
| `analytics-dev` | Analytics & Stats | S20–S23: Statistical Engine, Plotly Charts, Citations | [.agents/agents/06-analytics-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/06-analytics-dev.md) |
| `frontend-dev` | Next.js Developer | S24–S28: UI Shell, Query Input, Agent Monitor, Dashboard | [.agents/agents/07-frontend-dev.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/07-frontend-dev.md) |
| `test-engineer` | QA & Verification | S29–S32: Unit, Integration, Hallucination, Performance | [.agents/agents/08-test-engineer.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/08-test-engineer.md) |
| `doc-writer` | Technical Writer | S36–S38: README, ARCHITECTURE, TESTING, DATA_SOURCES | [.agents/agents/10-doc-writer.md](file:///Users/sathish/Documents/PolicyDataAnalytics/.agents/agents/10-doc-writer.md) |

---

## 3. Autonomous Execution Protocol

### Step A: Read LEDGER and Identify Unblocked Stories
- Read [LEDGER.md](file:///Users/sathish/Documents/PolicyDataAnalytics/LEDGER.md).
- Find rows where `Status = BACKLOG`.
- A story is **unblocked** if and only if all stories listed in its `Depends on` section are marked `DONE`.

### Step B: Parallel & Sequential Dispatch
- **Parallel Dispatch**: When two or more unblocked stories belong to different subsystems (e.g., Frontend setup `S24` and Database models `S02` once `S01` completes), launch them concurrently using `invoke_subagent`.
- **Sequential Dispatch**: If stories have shared dependencies, prioritize higher priority stories (`P0` → `P1` → `P2`) and lowest ID first.
- Update [LEDGER.md](file:///Users/sathish/Documents/PolicyDataAnalytics/LEDGER.md) status for dispatched stories from `BACKLOG` to `IN_PROGRESS`.

### Step C: Subagent Delegation Pattern
For each story to be executed, invoke a subagent:
```python
invoke_subagent(
    TypeName="self",
    Role=f"{agent_name} - Story {story_id}",
    Prompt=f"""
You are the {agent_name} agent for the Agentic Policy Data Analytics Platform.
Implement Story {story_id} in full.

Instructions: Read .agents/agents/{agent_file}.md
Story File: Read stories/{story_file}.md and satisfy ALL Acceptance Criteria.
Architecture Reference: Read LLD.md, HLD.md, and TECH_STACK.md.

Execute all code creation, file editing, and testing. Do not leave placeholder TODOs.
When completed, return a structured summary of deliverables and verification status.
"""
)
```

### Step D: Verification and Auto-Progression
- When a subagent completes and sends its result back:
  1. Inspect created files and run tests/builds if necessary.
  2. Verify all Acceptance Criteria checkboxes are satisfied.
  3. If verified, update [LEDGER.md](file:///Users/sathish/Documents/PolicyDataAnalytics/LEDGER.md):
     - Set `Status` → `DONE`
     - Set `Last Updated` → current date
     - Add concise summary of deliverables to `Comments`
     - Update the `Progress Summary` table numbers.
  4. If defects are found, message the subagent to fix them.
  5. **Immediately trigger Step A again** to pick newly unblocked stories. Do not pause.

---

## 4. Disturbance Threshold (When to Involve User)
- **Allowed without user input**: All file writing, editing, dependency installs, migrations, unit tests, code linting, documentation generation, and subagent orchestration.
- **Intervention required**:
  - A real external API key is mandatory and cannot be substituted with a mock provider (`MOCK_LLM=true`, `USE_MOCK_DATA_SOURCES=true`).
  - Explicit manual verification (`MANUAL_CHECK`) requested by user.
  - Fatal unrecoverable environment errors.
