"""Application configuration settings using Pydantic v2 Settings."""

import json
import logging
import warnings

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Core application settings and environment variables."""

    # 1. App Settings
    PROJECT_NAME: str = "Agentic Policy Data Analytics Platform"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    API_V1_STR: str = "/api/v1"

    # CORS
    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from JSON string, comma-separated string, or list."""
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except json.JSONDecodeError:
                    pass
            return [i.strip() for i in v_trimmed.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(item).strip() for item in v]
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def cors_origins(self) -> list[str]:
        """Accessor returning CORS origins as a list of strings."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [str(self.CORS_ORIGINS)]

    # 2. Database (Postgres)
    DATABASE_URL: str = (
        "postgresql+asyncpg://policy_user:policy_pass@localhost:5432/policy_analytics"
    )

    # 3. Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # 4. LLM Providers (OpenAI, Anthropic, Gemini, Bedrock, Mock mode)
    MOCK_LLM: bool = False
    PRIMARY_LLM_PROVIDER: str = "bedrock"
    FALLBACK_LLM_PROVIDER: str = "gemini"
    LLM_FALLBACK: bool = False
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_HEALTH_CHECK_CACHE_TTL: float = 60.0

    @property
    def mock_llm(self) -> bool:
        """Accessor for mock LLM mode flag."""
        import os
        env_val = os.environ.get("MOCK_LLM")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        return self.MOCK_LLM

    @property
    def primary_llm_provider(self) -> str:
        """Accessor for primary LLM provider identifier."""
        import os
        return os.environ.get("PRIMARY_LLM_PROVIDER", self.PRIMARY_LLM_PROVIDER)

    @property
    def fallback_llm_provider(self) -> str:
        """Accessor for fallback LLM provider identifier."""
        import os
        return os.environ.get("FALLBACK_LLM_PROVIDER", self.FALLBACK_LLM_PROVIDER)

    @property
    def llm_fallback(self) -> bool:
        """Accessor for LLM fallback enablement flag."""
        import os
        env_val = os.environ.get("LLM_FALLBACK")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        return self.LLM_FALLBACK

    @property
    def llm_timeout_seconds(self) -> float:
        """Accessor for default LLM timeout in seconds."""
        return self.LLM_TIMEOUT_SECONDS

    # Google Gemini
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_TIMEOUT_SECONDS: float = 30.0

    # Amazon Bedrock
    BEDROCK_API_KEY: str | None = None
    AWS_BEARER_TOKEN_BEDROCK: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "ap-south-2"
    AWS_DEFAULT_REGION: str = "ap-south-2"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    BEDROCK_TIMEOUT_SECONDS: float = 30.0

    # OpenAI & Anthropic (Fallbacks)
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    @property
    def openai_model(self) -> str:
        """Accessor for OpenAI model identifier."""
        return self.OPENAI_MODEL

    @property
    def anthropic_model(self) -> str:
        """Accessor for Anthropic model identifier."""
        return self.ANTHROPIC_MODEL

    @property
    def gemini_model(self) -> str:
        """Accessor for Gemini model identifier."""
        return self.GEMINI_MODEL

    @property
    def gemini_timeout_seconds(self) -> float:
        """Accessor for Gemini API call timeout in seconds."""
        return self.GEMINI_TIMEOUT_SECONDS or self.LLM_TIMEOUT_SECONDS or 30.0

    @property
    def bedrock_model_id(self) -> str:
        """Accessor for Bedrock model identifier."""
        return self.BEDROCK_MODEL_ID

    @property
    def bedrock_timeout_seconds(self) -> float:
        """Accessor for Amazon Bedrock API call timeout in seconds."""
        return self.BEDROCK_TIMEOUT_SECONDS or self.LLM_TIMEOUT_SECONDS or 30.0

    # 5. Data Sources (SingStat, Data.gov.sg, Mock data)
    USE_MOCK_DATA_SOURCES: bool = False
    USE_MOCK_DATA_AS_FALLBACK: bool = False
    SINGSTAT_MCP_ENABLED: bool = True
    SINGSTAT_MCP_URL: str | None = "https://chatwithsandra.singstat.gov.sg/mcp"
    SINGSTAT_API_KEY: str | None = None
    DATAGOV_API_TOKEN: str | None = None

    @property
    def use_mock_data_as_fallback(self) -> bool:
        """Accessor for whether mock data fallback is permitted when live APIs fail."""
        import os

        env_val = os.environ.get("USE_MOCK_DATA_AS_FALLBACK")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        return bool(self.USE_MOCK_DATA_AS_FALLBACK or self.USE_MOCK_DATA_SOURCES)

    # 6. Frontend Settings
    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"
    NEXT_PUBLIC_WS_URL: str = "ws://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_llm_config(self) -> "Settings":
        """Warn if LLM keys are absent when MOCK_LLM is disabled, allowing mock mode."""
        if not self.MOCK_LLM:
            has_gemini = bool(self.GEMINI_API_KEY)
            has_bedrock = bool(
                self.BEDROCK_API_KEY
                or self.AWS_BEARER_TOKEN_BEDROCK
                or (self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)
            )
            has_openai = bool(self.OPENAI_API_KEY)
            has_anthropic = bool(self.ANTHROPIC_API_KEY)

            if not any([has_gemini, has_bedrock, has_openai, has_anthropic]):
                msg = (
                    "No LLM provider credentials configured (GEMINI_API_KEY, BEDROCK credentials, "
                    "OPENAI_API_KEY, ANTHROPIC_API_KEY all missing) while MOCK_LLM=False. "
                    "Live LLM calls will fail unless keys are provided or MOCK_LLM=true is set."
                )
                logger.warning(msg)
                warnings.warn(msg, UserWarning, stacklevel=2)
            else:
                provider_keys = {
                    "gemini": has_gemini,
                    "bedrock": has_bedrock,
                    "openai": has_openai,
                    "anthropic": has_anthropic,
                }
                primary = self.PRIMARY_LLM_PROVIDER.lower()
                if not provider_keys.get(primary, False):
                    msg = (
                        f"Primary LLM provider '{self.PRIMARY_LLM_PROVIDER}' has no credentials configured. "
                        f"Fallback to '{self.FALLBACK_LLM_PROVIDER}' will occur if configured."
                    )
                    logger.warning(msg)
                    warnings.warn(msg, UserWarning, stacklevel=2)
        return self


settings = Settings()
