"""Pydantic schemas for agent workflow execution steps and event logs."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentStepType(StrEnum):
    """Categorization of agent execution steps."""

    THINK = "THINK"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    DONE = "DONE"
    ERROR = "ERROR"


class AgentName(StrEnum):
    """Core specialized agent personas in the multi-agent system."""

    COORDINATOR = "coordinator"
    EXTRACTION = "extraction"
    ANALYTICS = "analytics"


class AgentStepSchema(BaseModel):
    """Schema representing an individual step executed by an agent."""

    agent_name: str = Field(
        ...,
        description="Name of the agent executing the step (e.g., coordinator, extraction, analytics)",
    )
    step_type: str = Field(
        ...,
        description="Type of execution step: THINK | ACT | OBSERVE | DONE | ERROR",
    )
    content: dict[str, Any] = Field(
        ...,
        description="Detailed payload of the step: reasoning, tool parameters, observations, or errors",
    )
    sequence_no: int = Field(
        ...,
        ge=1,
        description="Monotonically increasing sequence number within the analysis execution",
    )


class AgentLogCreate(AgentStepSchema):
    """Schema for persisting an agent execution log entry in the database."""

    analysis_id: uuid.UUID = Field(
        ...,
        description="ID of the analysis pipeline run this log belongs to",
    )


class AgentLogResponse(BaseModel):
    """Public representation of an agent step log returned via REST or WebSocket."""

    id: uuid.UUID
    analysis_id: uuid.UUID
    agent_name: str
    step_type: str
    content: dict[str, Any]
    sequence_no: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
