"""Asynchronous CRUD operations for Dataset and AnalysisDataset models using SQLAlchemy 2.0."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import AnalysisDataset, Dataset


async def get_or_create_dataset(
    db: AsyncSession,
    source: str,
    source_id: str | None = None,
    data_hash: str | None = None,
    **kwargs: Any,
) -> tuple[Dataset, bool]:
    """Retrieve an existing cached dataset or create a new record if not present.

    Lookup strategy:
    1. If source_id is provided, look up by (source, source_id).
    2. If not found and data_hash is provided, look up by (source, data_hash).
    3. If still not found, create new Dataset record.

    Args:
        db: Active asynchronous database session.
        source: Provider source identifier (singstat, datagov, mom, etc.).
        source_id: Optional external dataset table/resource ID.
        data_hash: Optional SHA-256 fingerprint of dataset content.
        **kwargs: Additional attributes (title, row_count, columns, expires_at, id).

    Returns:
        tuple[Dataset, bool]: (Dataset instance, created flag where True means newly created).
    """
    dataset: Dataset | None = None

    if source_id is not None:
        stmt = select(Dataset).where(
            Dataset.source == source,
            Dataset.source_id == source_id,
        )
        result = await db.execute(stmt)
        dataset = result.scalar_one_or_none()

    if dataset is None and data_hash is not None:
        stmt = select(Dataset).where(
            Dataset.source == source,
            Dataset.data_hash == data_hash,
        )
        result = await db.execute(stmt)
        dataset = result.scalar_one_or_none()

    if dataset is not None:
        return dataset, False

    new_dataset = Dataset(
        id=kwargs.get("id") or uuid.uuid4(),
        source=source,
        source_id=source_id,
        data_hash=data_hash,
        title=kwargs.get("title"),
        row_count=kwargs.get("row_count"),
        columns=kwargs.get("columns"),
        expires_at=kwargs.get("expires_at"),
    )
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset, True


async def get_dataset(
    db: AsyncSession,
    id: uuid.UUID,
) -> Dataset | None:
    """Fetch an individual Dataset record by its primary key UUID.

    Args:
        db: Active asynchronous database session.
        id: Primary key UUID of the dataset.

    Returns:
        Dataset | None: Found dataset record or None if absent.
    """
    stmt = select(Dataset).where(Dataset.id == id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def link_dataset_to_analysis(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> AnalysisDataset:
    """Associate a dataset with an analysis job in the many-to-many junction table.

    Args:
        db: Active asynchronous database session.
        analysis_id: UUID of the parent analysis job.
        dataset_id: UUID of the cached dataset record.

    Returns:
        AnalysisDataset: Junction association record.
    """
    stmt = select(AnalysisDataset).where(
        AnalysisDataset.analysis_id == analysis_id,
        AnalysisDataset.dataset_id == dataset_id,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    association = AnalysisDataset(
        analysis_id=analysis_id,
        dataset_id=dataset_id,
    )
    db.add(association)
    await db.commit()
    return association


async def get_datasets_for_analysis(
    db: AsyncSession,
    analysis_id: uuid.UUID,
) -> list[Dataset]:
    """Retrieve all datasets associated with a given analysis job.

    Args:
        db: Active asynchronous database session.
        analysis_id: UUID of the analysis.

    Returns:
        list[Dataset]: List of associated Dataset instances.
    """
    stmt = (
        select(Dataset)
        .join(AnalysisDataset, AnalysisDataset.dataset_id == Dataset.id)
        .where(AnalysisDataset.analysis_id == analysis_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
