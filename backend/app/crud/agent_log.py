"""Asynchronous CRUD operations for AgentLog model using SQLAlchemy 2.0."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_log import AgentLog


async def create_agent_log(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    agent_name: str,
    step_type: str,
    content: dict[str, Any],
    seq_no: int,
    log_id: uuid.UUID | None = None,
) -> AgentLog:
    """Create a new agent execution step log entry.

    Args:
        db: Active asynchronous database session.
        analysis_id: UUID of parent analysis job.
        agent_name: Name of agent (coordinator, extraction, analytics).
        step_type: Step type identifier (THINK, ACT, OBSERVE, DONE, ERROR).
        content: JSON dictionary capturing agent thought, tool call, or output.
        seq_no: Monotonically increasing step number for ordering.
        log_id: Optional UUID. If omitted, a fresh UUID is generated.

    Returns:
        AgentLog: Persisted and refreshed AgentLog instance.
    """
    log_entry = AgentLog(
        id=log_id or uuid.uuid4(),
        analysis_id=analysis_id,
        agent_name=agent_name,
        step_type=step_type,
        content=content,
        sequence_no=seq_no,
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    return log_entry


async def list_agent_logs(
    db: AsyncSession,
    analysis_id: uuid.UUID,
) -> list[AgentLog]:
    """Retrieve all step logs for a given analysis ordered by sequence_no ascending.

    Args:
        db: Active asynchronous database session.
        analysis_id: UUID of the parent analysis job.

    Returns:
        list[AgentLog]: Agent logs ordered by sequence_no.
    """
    stmt = (
        select(AgentLog)
        .where(AgentLog.analysis_id == analysis_id)
        .order_by(AgentLog.sequence_no.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_agent_log(
    db: AsyncSession,
    id: uuid.UUID,
) -> AgentLog | None:
    """Fetch an individual AgentLog entry by its primary key UUID.

    Args:
        db: Active asynchronous database session.
        id: Primary key UUID of the agent log.

    Returns:
        AgentLog | None: Found record or None if absent.
    """
    stmt = select(AgentLog).where(AgentLog.id == id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
