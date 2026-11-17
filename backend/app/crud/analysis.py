"""Asynchronous CRUD operations for Analysis model using SQLAlchemy 2.0."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import Analysis
from app.schemas.analysis import AnalysisStatus


async def create_analysis(
    db: AsyncSession,
    query: str,
    metadata: dict[str, Any] | None = None,
    analysis_id: uuid.UUID | None = None,
    status: str | AnalysisStatus = AnalysisStatus.PENDING,
) -> Analysis:
    """Create a new Analysis record and persist it to the database.

    Args:
        db: Active asynchronous database session.
        query: User input query text describing the policy data question.
        metadata: Optional contextual metadata (sources, plan parameters, etc.).
        analysis_id: Optional UUID. If omitted, a fresh UUID is generated.
        status: Initial status for the job, defaults to PENDING.

    Returns:
        Analysis: Persisted and refreshed ORM Analysis instance.
    """
    status_str = status.value if isinstance(status, AnalysisStatus) else str(status)
    analysis = Analysis(
        id=analysis_id or uuid.uuid4(),
        query=query,
        status=status_str,
        metadata_=metadata,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


async def get_analysis(
    db: AsyncSession,
    id: uuid.UUID,
    include_deleted: bool = False,
    include_logs: bool = False,
) -> Analysis | None:
    """Fetch a single Analysis record by its primary key UUID.

    Args:
        db: Active asynchronous database session.
        id: Primary key UUID of the analysis.
        include_deleted: If True, returns the record even if status is 'DELETED'.
        include_logs: If True, eagerly loads related agent_logs ordered by sequence_no.

    Returns:
        Analysis | None: Found record or None if absent or soft-deleted.
    """
    stmt = select(Analysis).where(Analysis.id == id)
    if not include_deleted:
        stmt = stmt.where(Analysis.status != AnalysisStatus.DELETED.value)
    if include_logs:
        stmt = stmt.options(selectinload(Analysis.agent_logs))

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_analyses(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    include_deleted: bool = False,
) -> list[Analysis]:
    """Retrieve a paginated list of analyses ordered by creation time descending.

    Args:
        db: Active asynchronous database session.
        skip: Offset for pagination.
        limit: Maximum number of records to return.
        include_deleted: If True, includes soft-deleted records.

    Returns:
        list[Analysis]: List of matching Analysis instances.
    """
    stmt = select(Analysis)
    if not include_deleted:
        stmt = stmt.where(Analysis.status != AnalysisStatus.DELETED.value)
    stmt = stmt.order_by(Analysis.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_analyses(
    db: AsyncSession,
    include_deleted: bool = False,
) -> int:
    """Count the total number of analyses matching the active filter.

    Args:
        db: Active asynchronous database session.
        include_deleted: If True, includes soft-deleted records in the count.

    Returns:
        int: Total number of matching records.
    """
    stmt = select(func.count()).select_from(Analysis)
    if not include_deleted:
        stmt = stmt.where(Analysis.status != AnalysisStatus.DELETED.value)

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_analysis_status(
    db: AsyncSession,
    id: uuid.UUID,
    status: str | AnalysisStatus,
    result: dict[str, Any] | None = None,
    error_msg: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Analysis | None:
    """Update execution status, final results, or error details of an Analysis.

    Args:
        db: Active asynchronous database session.
        id: Primary key UUID of the analysis.
        status: New lifecycle status (PENDING, RUNNING, DONE, FAILED, DELETED).
        result: Optional final analysis payload (insights, charts, citations).
        error_msg: Optional error description string if analysis failed.
        metadata: Optional updated metadata dict.

    Returns:
        Analysis | None: Updated Analysis instance, or None if not found.
    """
    analysis = await get_analysis(db, id, include_deleted=True)
    if analysis is None:
        return None

    status_str = status.value if isinstance(status, AnalysisStatus) else str(status)
    analysis.status = status_str
    if result is not None:
        analysis.result = result
    if error_msg is not None:
        analysis.error_msg = error_msg
    if metadata is not None:
        analysis.metadata_ = metadata

    await db.commit()
    await db.refresh(analysis)
    return analysis


async def delete_analysis(
    db: AsyncSession,
    id: uuid.UUID,
    soft: bool = True,
) -> bool:
    """Delete an analysis record. Soft delete sets status='DELETED' without removing row.

    Args:
        db: Active asynchronous database session.
        id: Primary key UUID of the analysis.
        soft: If True (default), marks status as 'DELETED'. If False, deletes row from DB.

    Returns:
        bool: True if an existing active record was deleted/updated, False otherwise.
    """
    analysis = await get_analysis(db, id, include_deleted=True)
    if analysis is None:
        return False

    if soft:
        if analysis.status == AnalysisStatus.DELETED.value:
            return False  # Already soft deleted
        analysis.status = AnalysisStatus.DELETED.value
        await db.commit()
        return True

    await db.delete(analysis)
    await db.commit()
    return True
