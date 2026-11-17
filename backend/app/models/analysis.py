"""SQLAlchemy ORM model for analysis queries and results."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.agent_log import AgentLog
    from app.models.dataset import Dataset


class Analysis(Base):
    """Top-level record representing a user policy data query and analysis pipeline execution."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )
    error_msg: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    agent_logs: Mapped[list["AgentLog"]] = relationship(
        "AgentLog",
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="AgentLog.sequence_no",
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset",
        secondary="analysis_datasets",
        back_populates="analyses",
    )

    def __repr__(self) -> str:
        return f"<Analysis(id={self.id}, status='{self.status}', query='{self.query[:30]}...')>"
