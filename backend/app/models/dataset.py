"""SQLAlchemy ORM models for external datasets and analysis associations."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class AnalysisDataset(Base):
    """Many-to-many association mapping between analyses and cached datasets."""

    __tablename__ = "analysis_datasets"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        return f"<AnalysisDataset(analysis_id={self.analysis_id}, dataset_id={self.dataset_id})>"


class Dataset(Base):
    """External or cached dataset used for policy analytics computations."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    source_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    data_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    row_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    columns: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    analyses: Mapped[list["Analysis"]] = relationship(
        "Analysis",
        secondary="analysis_datasets",
        back_populates="datasets",
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, source='{self.source}', title='{self.title}')>"
