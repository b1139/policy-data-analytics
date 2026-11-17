"""WebSocket streaming endpoint for real-time policy data analysis step updates."""

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.core.database import get_db
from app.crud.agent_log import list_agent_logs
from app.crud.analysis import get_analysis
from app.schemas.analysis import AnalysisStatus
from app.schemas.websocket import WSMessageType
from app.services.pubsub import (
    format_agent_step_message,
    format_complete_message,
    format_error_message,
    format_status_change_message,
    subscribe_steps,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def _replay_persisted_steps(
    websocket: WebSocket, db: AsyncSession, analysis_id: uuid.UUID
) -> None:
    """Send previously persisted agent steps so late/returning clients see the full feed."""
    try:
        logs = await list_agent_logs(db, analysis_id)
        for log in logs:
            ts = log.created_at.isoformat() if log.created_at else datetime.now(UTC).isoformat()
            msg = format_agent_step_message(
                analysis_id=analysis_id,
                agent_name=str(log.agent_name),
                step_type=str(log.step_type),
                content=log.content or {},
                sequence_no=int(log.sequence_no or 0),
            )
            msg["timestamp"] = ts
            await websocket.send_text(json.dumps(msg, default=str))
    except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
        raise
    except Exception as exc:
        logger.warning("Failed to replay persisted steps for %s: %s", analysis_id, exc)


@router.websocket("/ws/analysis/{analysis_id}")
async def websocket_analysis_endpoint(
    websocket: WebSocket,
    analysis_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ping_interval: float = Query(
        default=60.0,
        description="Interval in seconds between WebSocket keepalive ping frames.",
    ),
) -> None:
    """Stream real-time agent execution events and reasoning steps for an analysis run.

    Subscribes to the analysis Redis pub/sub channel `analysis:{id}:steps` and forwards
    published messages verbatim to the connected client. Features automated keepalive
    ping/pong heartbeat loop (60s default) and graceful disconnect handling.

    Client connections for non-existent or invalid analysis UUIDs receive a structured
    error frame before the socket is closed with status 1008 (Policy Violation).

    Args:
        websocket: FastAPI WebSocket connection instance.
        analysis_id: Target analysis UUID or raw string parameter.
        db: Injected asynchronous database session dependency.
        ping_interval: Seconds between ping keepalive packets (defaults to 60s).
    """
    # 1. Validate analysis_id UUID format
    try:
        parsed_id = uuid.UUID(analysis_id)
    except (ValueError, TypeError):
        logger.warning("Rejected WebSocket connection: invalid UUID format '%s'", analysis_id)
        await websocket.accept()
        err_msg = format_error_message(
            analysis_id=analysis_id,
            error="Invalid analysis UUID format",
            details={"detail": f"Provided analysis ID '{analysis_id}' is not a valid UUID."},
        )
        await websocket.send_text(json.dumps(err_msg, default=str))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Check analysis existence in database
    analysis = await get_analysis(db, parsed_id)
    if analysis is None:
        logger.warning("Rejected WebSocket connection: analysis '%s' not found", parsed_id)
        await websocket.accept()
        err_msg = format_error_message(
            analysis_id=parsed_id,
            error="Analysis not found",
            details={"detail": f"Analysis with ID '{analysis_id}' does not exist."},
        )
        await websocket.send_text(json.dumps(err_msg, default=str))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Handle already completed or failed analyses
    if analysis.status in (AnalysisStatus.DONE, AnalysisStatus.FAILED):
        logger.debug(
            "WebSocket connecting to terminal analysis '%s' (status: %s)",
            parsed_id,
            analysis.status,
        )
        await websocket.accept()
        await _replay_persisted_steps(websocket, db, parsed_id)
        if analysis.status == AnalysisStatus.DONE:
            complete_msg = format_complete_message(
                analysis_id=parsed_id,
                result=analysis.result or {},
            )
            await websocket.send_text(json.dumps(complete_msg, default=str))
        else:
            fail_msg = format_error_message(
                analysis_id=parsed_id,
                error=analysis.error_msg or "Analysis execution failed.",
            )
            await websocket.send_text(json.dumps(fail_msg, default=str))
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        return

    # 4. Accept connection for in-progress or queued analyses
    await websocket.accept()
    logger.info("Accepted WebSocket connection for analysis_id=%s", parsed_id)
    await _replay_persisted_steps(websocket, db, parsed_id)

    # Send initial status frame
    init_msg = format_status_change_message(
        analysis_id=parsed_id,
        status=analysis.status,
        details={"message": "Connected to real-time analysis streaming channel."},
    )
    await websocket.send_text(json.dumps(init_msg, default=str))

    stop_event = asyncio.Event()

    async def pubsub_worker() -> None:
        """Stream messages from pub/sub channel verbatim to WebSocket client."""
        try:
            async for raw_message in subscribe_steps(parsed_id):
                if stop_event.is_set():
                    break

                # Forward verbatim from Redis / pubsub to WebSocket client
                await websocket.send_text(raw_message)

                # Inspect message type for terminal condition
                try:
                    parsed = json.loads(raw_message)
                    type_str = str(parsed.get("type", "")).lower()
                    if type_str in ("complete", "error", "analysis_done", "analysis_error"):
                        logger.debug("Terminal step received for %s; ending stream", parsed_id)
                        stop_event.set()
                        break
                except Exception:
                    pass
        except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
            stop_event.set()
        except Exception as exc:
            logger.error("Error in pubsub worker for %s: %s", parsed_id, exc, exc_info=True)
            stop_event.set()

    async def ping_worker() -> None:
        """Send periodic keepalive ping messages to the connected client."""
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=ping_interval)
                    break
                except TimeoutError:
                    pass

                if stop_event.is_set():
                    break

                ping_payload = json.dumps(
                    {
                        "type": WSMessageType.PING.value,
                        "analysis_id": str(parsed_id),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {},
                    }
                )
                await websocket.send_text(ping_payload)
        except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
            stop_event.set()
        except Exception as exc:
            logger.debug("Ping loop closed for %s: %s", parsed_id, exc)
            stop_event.set()

    tasks = [
        asyncio.create_task(pubsub_worker()),
        asyncio.create_task(ping_worker()),
    ]

    try:
        await asyncio.gather(*tasks)
    except (WebSocketDisconnect, ConnectionClosed) as exc:
        logger.info("WebSocket disconnected cleanly for analysis_id=%s: %s", parsed_id, exc)
    except Exception as exc:
        logger.error(
            "WebSocket streaming error for analysis_id=%s: %s",
            parsed_id,
            exc,
            exc_info=True,
        )
    finally:
        stop_event.set()
        for t in tasks:
            if not t.done():
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
        with contextlib.suppress(Exception):
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        logger.debug("WebSocket session closed cleanly for analysis_id=%s", parsed_id)
