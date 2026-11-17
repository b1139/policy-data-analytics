# S26 — Real-time Agent Activity Monitor
**Epic**: E6 Frontend | **Priority**: P0 | **Assigned**: frontend-dev  
**Depends on**: S25, S07

## Description
Build the real-time agent activity monitor: a live feed of agent reasoning steps delivered via WebSocket, with visual differentiation by agent and step type. This is the most compelling feature of the UI.

## Acceptance Criteria
- [x] `frontend/hooks/useWebSocket.ts` — custom hook:
  - Connects to `ws://{WS_URL}/ws/analysis/{id}`
  - Auto-reconnects on disconnect (max 3 attempts, exponential backoff)
  - Returns: `{steps: AgentStep[], isConnected: bool, isDone: bool, error: string | null}`
  - Accumulates steps in state array
- [x] `frontend/components/agents/AgentMonitor.tsx`
  - Renders `AgentStep` list as a feed
  - Auto-scrolls to latest step (smooth scroll)
  - Step row: `[timestamp] [agent badge] [step_type icon] content`
  - Agent badge colors: Coordinator=blue, Extraction=green, Analytics=purple
  - Step type icons: THINK=💭, ACT=⚡, OBSERVE=👁️, DONE=✅, ERROR=❌
  - THINK steps: italic text
  - ACT steps: monospace + tool name highlighted
  - OBSERVE steps: indented, lighter text
- [x] `frontend/components/agents/AgentStatusBar.tsx`
  - Shows current agent name + animated spinner while running
  - Shows "Analysis complete" when DONE
  - Shows "Analysis failed" with error on ERROR
- [x] Empty state: "Waiting for agents to start..." with pulsing dots

## Technical Notes
- Steps rendered with `React.memo` to avoid re-renders
- WebSocket cleanup in `useEffect` return function
- Max 500 steps displayed (virtualized list if more)
