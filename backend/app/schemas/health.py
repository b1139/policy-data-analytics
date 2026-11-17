"""Pydantic schema for platform health check responses."""

from pydantic import BaseModel, ConfigDict, Field


class LLMProviderHealth(BaseModel):
    """Health status representation for a single LLM provider."""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(
        ...,
        description="Provider identifier (e.g., 'gemini', 'bedrock', 'mock').",
        examples=["gemini"],
    )
    status: str = Field(
        ...,
        description="Health status of the provider ('ok' or 'error').",
        examples=["ok"],
    )
    latency_ms: float | None = Field(
        default=None,
        description="Health check probe ping latency in milliseconds.",
        examples=[12.5],
    )


class LLMHealthStatus(BaseModel):
    """Container schema for primary and fallback LLM provider statuses."""

    model_config = ConfigDict(from_attributes=True)

    primary: LLMProviderHealth = Field(
        ...,
        description="Primary LLM provider health status.",
    )
    fallback: LLMProviderHealth = Field(
        ...,
        description="Fallback LLM provider health status.",
    )


class HealthResponse(BaseModel):
    """Schema representing the health status of platform services."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        ...,
        description="Overall platform health status, typically 'ok' or 'degraded'.",
        examples=["ok"],
    )
    db: str = Field(
        ...,
        description="PostgreSQL database connectivity status: 'ok' or 'error'.",
        examples=["ok", "error"],
    )
    redis: str = Field(
        ...,
        description="Redis async connection status: 'ok' or 'error'.",
        examples=["ok", "error"],
    )
    llm: LLMHealthStatus | None = Field(
        default=None,
        description="Health status of primary and fallback LLM providers.",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp indicating when the check was performed.",
        examples=["2026-11-16T03:45:00Z"],
    )
    environment: str = Field(
        default="development",
        description="Current runtime environment (development, staging, production).",
        examples=["development"],
    )
