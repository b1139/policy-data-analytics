"""Unit tests for configuration management (app.core.config.Settings)."""

from pathlib import Path
import warnings

import pytest

from app.core.config import Settings


def test_settings_defaults():
    """Verify default configuration values."""
    s = Settings(MOCK_LLM=True, _env_file=None)
    assert s.PROJECT_NAME == "Agentic Policy Data Analytics Platform"
    assert s.ENVIRONMENT == "development"
    assert s.LOG_LEVEL == "INFO"
    assert s.API_V1_STR == "/api/v1"
    assert s.PRIMARY_LLM_PROVIDER == "bedrock"
    assert s.FALLBACK_LLM_PROVIDER == "gemini"
    assert s.LLM_FALLBACK is False
    assert s.llm_fallback is False
    assert s.LLM_TIMEOUT_SECONDS == 30.0
    assert s.GEMINI_TIMEOUT_SECONDS == 30.0
    assert s.gemini_timeout_seconds == 30.0
    assert s.BEDROCK_TIMEOUT_SECONDS == 30.0
    assert s.bedrock_timeout_seconds == 30.0
    assert s.USE_MOCK_DATA_AS_FALLBACK is False
    assert "http://localhost:3000" in s.CORS_ORIGINS


def test_settings_model_config():
    """Verify pydantic SettingsConfigDict parameters."""
    assert Settings.model_config.get("env_file") == ".env"
    assert Settings.model_config.get("extra") == "ignore"


def test_cors_origins_parsing():
    """Test parsing CORS origins from list, comma-separated string, and JSON array."""
    # List
    s1 = Settings(CORS_ORIGINS=["http://localhost:3000", "http://example.com"], MOCK_LLM=True)
    assert s1.CORS_ORIGINS == ["http://localhost:3000", "http://example.com"]

    # Comma-separated string
    s2 = Settings(CORS_ORIGINS="http://localhost:3000, https://app.example.com", MOCK_LLM=True)
    assert s2.CORS_ORIGINS == ["http://localhost:3000", "https://app.example.com"]

    # JSON array string
    s3 = Settings(CORS_ORIGINS='["http://localhost:3000", "http://127.0.0.1:3000"]', MOCK_LLM=True)
    assert s3.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_validate_llm_config_mock_mode_allows_empty_keys():
    """Verify mock mode (MOCK_LLM=True) does not trigger warnings when keys are absent."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        s = Settings(
            MOCK_LLM=True,
            GEMINI_API_KEY=None,
            BEDROCK_API_KEY=None,
            OPENAI_API_KEY=None,
            ANTHROPIC_API_KEY=None,
        )
        assert s.MOCK_LLM is True
        # Filter for UserWarning from config
        config_warnings = [w for w in recorded_warnings if issubclass(w.category, UserWarning)]
        assert len(config_warnings) == 0


def test_validate_llm_config_warns_when_all_keys_absent():
    """Verify warning is emitted if MOCK_LLM=False and all provider keys are absent."""
    with pytest.warns(UserWarning, match="No LLM provider credentials configured"):
        Settings(
            MOCK_LLM=False,
            GEMINI_API_KEY=None,
            BEDROCK_API_KEY=None,
            AWS_BEARER_TOKEN_BEDROCK=None,
            AWS_ACCESS_KEY_ID=None,
            AWS_SECRET_ACCESS_KEY=None,
            OPENAI_API_KEY=None,
            ANTHROPIC_API_KEY=None,
        )


def test_validate_llm_config_warns_when_primary_missing():
    """Verify warning when primary LLM key is absent but fallback is configured."""
    with pytest.warns(
        UserWarning, match="Primary LLM provider 'gemini' has no credentials configured"
    ):
        Settings(
            MOCK_LLM=False,
            PRIMARY_LLM_PROVIDER="gemini",
            GEMINI_API_KEY=None,
            BEDROCK_API_KEY="test-bedrock-token",
        )


def test_validate_llm_config_clean_when_primary_provided():
    """Verify no warning when primary provider key is supplied."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        s = Settings(
            MOCK_LLM=False,
            PRIMARY_LLM_PROVIDER="gemini",
            GEMINI_API_KEY="test-gemini-key",
        )
        assert s.GEMINI_API_KEY == "test-gemini-key"
        config_warnings = [w for w in recorded_warnings if issubclass(w.category, UserWarning)]
        assert len(config_warnings) == 0


def test_settings_covers_all_env_example_vars():
    """Verify all variables declared in .env.example are represented in Settings."""
    env_example_path = Path(".env.example")
    if not env_example_path.exists():
        env_example_path = Path(__file__).resolve().parents[3] / ".env.example"
    if not env_example_path.exists():
        env_example_path = Path(__file__).resolve().parents[2] / ".env.example"
    with open(env_example_path, encoding="utf-8") as f:
        lines = f.readlines()

    env_vars = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            var_name = line.split("=", 1)[0].strip()
            env_vars.add(var_name)

    settings_fields = set(Settings.model_fields.keys())
    missing_fields = env_vars - settings_fields
    assert not missing_fields, f"Missing fields in Settings: {missing_fields}"
