---
name: orchestrator
description: Autonomous SDLC Orchestrator for the Agentic Policy Data Analytics Platform. Drives all 38 development stories from BACKLOG to DONE autonomously using parallel subagents, continuous dependency resolution, and automated verification without unnecessary manual intervention.
---

# Autonomous SDLC Orchestrator Skill

This skill guides the agent in orchestrating the complete implementation of the **Agentic Policy Data Analytics Platform**.

## When Activated
Activate this skill whenever the user says:
- `"start"`
- `"start orchestrator"`
- `"run orchestrator"`
- `"continue project"`

## Operational Principles
1. **Zero Unnecessary User Interruptions**: Do not pause between stories to ask for approval. Verify each story against its Acceptance Criteria programmatically, mark it `DONE` in `LEDGER.md`, and advance immediately.
2. **Subagent Delegation**: Dispatch implementation tasks to specialized subagents (`architect`, `backend-dev`, `frontend-dev`, etc.) using `invoke_subagent`.
3. **Parallel Execution**: Where stories have disjoint dependency paths (e.g., frontend setup vs database schema), dispatch multiple subagents in parallel.
4. **Shared Ledger as Single Source of Truth**: Continuously read and update `LEDGER.md` after each story state transition.

## Execution Algorithm
1. Read `LEDGER.md`.
2. Evaluate story dependencies from `stories/S##-*.md`.
3. Select all unblocked `BACKLOG` stories.
4. For each ready story:
   - Mark `IN_PROGRESS` in `LEDGER.md`.
   - Dispatch subagent via `invoke_subagent` with the agent's instructions, story criteria, and architecture specs.
5. Upon subagent completion:
   - Check deliverables against story Acceptance Criteria.
   - Run verification commands (tests, builds, typechecks) if applicable.
   - Update `LEDGER.md` status to `DONE` and update Progress Summary counts.
6. Check for newly unblocked stories and repeat until all 38 stories are `DONE`.
7. Alert user only if a genuine blocker or manual secret entry is needed.
