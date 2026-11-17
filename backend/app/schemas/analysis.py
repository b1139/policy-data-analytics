"""Pydantic schemas for analysis requests, responses, and state management."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.agent import AgentLogResponse


class AnalysisStatus(StrEnum):
    """Possible lifecycle states for an analysis job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    DELETED = "DELETED"


class AnalysisCreate(BaseModel):
    """Payload to initiate a new policy data analysis request."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=10000,
        description="Natural language policy research query",
        examples=["What is the 5-year trend in Singapore's consumer price index (CPI)?"],
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional contextual configuration, e.g., preferred data sources or date limits",
    )


class AnalysisStartRequest(BaseModel):
    """Payload to initiate a new policy analysis pipeline execution via REST API."""

    query: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language policy research query (must be between 10 and 2000 non-empty characters)",
        examples=["What is the 5-year trend in Singapore's consumer price index (CPI)?"],
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional contextual configuration, e.g., preferred data sources or date limits",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, value: str) -> str:
        """Validate that query is not empty or pure whitespace and adheres to length bounds."""
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("Query must contain at least 10 non-whitespace characters.")
        if len(stripped) > 2000:
            raise ValueError("Query must not exceed 2000 characters.")
        return stripped


class AnalysisStartResponse(BaseModel):
    """Response returned upon successfully creating and enqueuing an analysis."""

    analysis_id: uuid.UUID = Field(
        ...,
        description="Unique identifier for the initiated analysis pipeline",
    )
    status: str = Field(
        ...,
        description="Initial execution status, typically 'PENDING'",
    )
    ws_url: str = Field(
        ...,
        description="WebSocket streaming URL for receiving real-time agent steps and updates",
    )


class AnalysisUpdate(BaseModel):
    """Payload to update an existing analysis job's status or results."""

    status: AnalysisStatus | None = None
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    error_msg: str | None = None


class AnalysisListItem(BaseModel):
    """Lightweight representation of an analysis for listing views."""

    id: uuid.UUID
    query: str
    status: AnalysisStatus
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisListResponse(BaseModel):
    """Paginated list envelope for analysis records."""

    items: list[AnalysisListItem] = Field(
        default_factory=list,
        description="List of analysis summaries",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of matching analysis records in the database",
    )
    skip: int = Field(
        ...,
        ge=0,
        description="Number of records skipped for pagination",
    )
    limit: int = Field(
        ...,
        ge=1,
        description="Maximum number of records requested",
    )


class AnalysisResponse(BaseModel):
    """Full detailed representation of an analysis including final results and metadata."""

    id: uuid.UUID
    query: str
    status: AnalysisStatus
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime
    agent_logs: list[AgentLogResponse] = Field(
        default_factory=list,
        description="Chronological log of agent execution steps",
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_orm_attributes(cls, data: Any) -> Any:
        """Resolve metadata_ attribute from SQLAlchemy ORM model into metadata and ensure agent_logs."""
        if hasattr(data, "metadata_"):
            return {
                "id": getattr(data, "id", None),
                "query": getattr(data, "query", None),
                "status": getattr(data, "status", None),
                "result": getattr(data, "result", None),
                "metadata": getattr(data, "metadata_", None),
                "error_msg": getattr(data, "error_msg", None),
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
                "agent_logs": getattr(data, "agent_logs", []),
            }
        return data


# Re-export report schemas for convenience
from app.schemas.report import AnalysisResult, ChartSpec, Citation  # noqa: E402

__all__ = [
    "AnalysisStatus",
    "AnalysisCreate",
    "AnalysisStartRequest",
    "AnalysisStartResponse",
    "AnalysisUpdate",
    "AnalysisListItem",
    "AnalysisListResponse",
    "AnalysisResponse",
    "Citation",
    "ChartSpec",
    "AnalysisResult",
]
