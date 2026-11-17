"""SQLAlchemy ORM model for agent execution logs."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class AgentLog(Base):
    """Execution step log captured during agent graph execution."""

    __tablename__ = "agent_logs"
    __table_args__ = (Index("idx_agent_logs_analysis", "analysis_id", "sequence_no"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    step_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship back to Analysis
    analysis: Mapped["Analysis"] = relationship(
        "Analysis",
        back_populates="agent_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<AgentLog(id={self.id}, agent='{self.agent_name}', "
            f"step='{self.step_type}', seq={self.sequence_no})>"
        )
