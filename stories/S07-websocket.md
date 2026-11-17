# S07 — WebSocket & Async Task Processing
**Epic**: E1 Backend Core | **Priority**: P1 | **Assigned**: backend-dev  
**Depends on**: S06

## Description
Implement the WebSocket endpoint for real-time agent step streaming using Redis pub/sub. Any backend service can publish a step to Redis; the WebSocket handler forwards it to the connected frontend client.

## Acceptance Criteria
- [ ] `WS /ws/analysis/{id}` endpoint accepts connections and sends messages
- [ ] WebSocket handler subscribes to Redis channel `analysis:{id}:steps`
- [ ] Messages forwarded verbatim from Redis to WebSocket client
- [ ] Connection handles: client disconnect (clean close), invalid analysis_id (send error + close)
- [ ] `backend/app/services/pubsub.py` — `publish_step(analysis_id, step_dict)` async function
- [ ] `publish_step` serializes dict to JSON and publishes to `analysis:{id}:steps`
- [ ] On analysis DONE/FAILED: publish final message then close channel
- [ ] WebSocket handler has 60s ping/pong keepalive
- [ ] Multiple simultaneous WS connections to same analysis_id all receive messages
- [ ] Message format matches LLD.md §7 exactly

## Technical Notes
- Use `redis.asyncio` client for async pub/sub
- Use `asyncio.gather()` for concurrent pub/sub listen + ping loop
- Handle `websockets.exceptions.ConnectionClosed` gracefully (log, clean up)
- Pub/sub subscription: `await pubsub.subscribe(f"analysis:{id}:steps")`
