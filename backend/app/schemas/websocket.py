"""Pydantic schemas and types for WebSocket streaming messages."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WSMessageType(StrEnum):
    """Supported WebSocket message types conforming to LLD §7 and platform events."""

    AGENT_STEP = "agent_step"
    STATUS_CHANGE = "status_change"
    ERROR = "error"
    COMPLETE = "complete"
    PING = "ping"
    PONG = "pong"
    # LLD §7 uppercase aliases
    AGENT_STEP_UPPER = "AGENT_STEP"
    ANALYSIS_DONE_UPPER = "ANALYSIS_DONE"
    ANALYSIS_ERROR_UPPER = "ANALYSIS_ERROR"


class WSMessage(BaseModel):
    """Schema for messages streamed over WebSocket during policy analysis."""

    type: str = Field(
        ...,
        description="Event type: agent_step, status_change, error, complete, ping, pong",
    )
    analysis_id: str = Field(
        ...,
        description="UUID string of the target analysis session",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 UTC timestamp of the event",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload conforming to step or status specification",
    )
    # Top-level fields for LLD.md §7 direct compatibility
    agent: str | None = Field(
        default=None,
        description="Persona of the agent (coordinator, extraction, analytics)",
    )
    step_type: str | None = Field(
        default=None,
        description="Type of execution step: THINK, ACT, OBSERVE, DONE, ERROR",
    )
    sequence_no: int | None = Field(
        default=None,
        description="Sequence number of the agent step",
    )
    content: dict[str, Any] | None = Field(
        default=None,
        description="Agent reasoning, tool invocations, observations or partial outputs",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Final aggregated analysis result (insights, charts, citations)",
    )
    error: str | None = Field(
        default=None,
        description="Error detail string if execution encountered an error",
    )
