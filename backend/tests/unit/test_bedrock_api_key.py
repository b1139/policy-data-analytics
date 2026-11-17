"""Unit tests specifically verifying Bedrock API Key (ABSK bearer token) authentication and error handling."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from botocore import UNSIGNED
from langchain_core.messages import AIMessage

from app.llm.bedrock_provider import BedrockProvider
from app.llm.exceptions import LLMProviderError


class TestBedrockApiKey:
    """Test suite for Bedrock API Key bearer token authentication."""

    def test_bedrock_api_key_only_initialization(self) -> None:
        """Verify client initializes correctly when only bedrock_api_key is provided and IAM keys are empty/whitespace."""
        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="us-east-1",
            aws_access_key_id="   ",
            aws_secret_access_key="",
            bedrock_api_key="ABSK_test_token_12345",
        )
        assert provider._client is not None
        boto_client = provider._client.client
        assert boto_client.meta.config.signature_version is UNSIGNED

        dummy_request = MagicMock()
        dummy_request.headers = {}
        boto_client.meta.events.emit(
            "before-sign.bedrock-runtime.Converse",
            request=dummy_request,
        )
        assert dummy_request.headers.get("Authorization") == "Bearer ABSK_test_token_12345"

    def test_bedrock_api_key_strip_quotes_and_bearer_prefix(self) -> None:
        """Verify provider cleans leading 'Bearer ' and extraneous quotes from bedrock_api_key."""
        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="us-west-2",
            bedrock_api_key='  "Bearer ABSK_quoted_token_999"  ',
        )
        assert provider._client is not None
        boto_client = provider._client.client

        dummy_request = MagicMock()
        dummy_request.headers = {}
        boto_client.meta.events.emit(
            "before-sign.bedrock-runtime.Converse",
            request=dummy_request,
        )
        assert dummy_request.headers.get("Authorization") == "Bearer ABSK_quoted_token_999"

    def test_bedrock_api_key_colon_separated_key_secret(self) -> None:
        """Verify colon-separated access_key:secret_key pairs are supported for legacy API key inputs."""
        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="us-east-1",
            bedrock_api_key="AKIA1234567890:my_secret_aws_key",
        )
        assert provider._client is not None
        boto_client = provider._client.client
        assert boto_client.meta.config.signature_version != UNSIGNED

    def test_bedrock_api_key_opt_in_region_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify a warning is logged when using a Bedrock API Key in an opt-in region like ap-south-2."""
        with caplog.at_level("WARNING"):
            _ = BedrockProvider(
                model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
                region_name="ap-south-2",
                bedrock_api_key="ABSK_test_token",
            )
        assert any("opt-in AWS region that may not support Bedrock API Key" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_error_002_translation(self) -> None:
        """Verify Error 002 (Bedrock models not allowed for account) is translated to a helpful non-retryable error."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            side_effect=Exception(
                "An error occurred (ValidationException) when calling the Converse operation: "
                "Error 002: Access to Bedrock models is not allowed for this account"
            )
        )
        mock_client.bind.return_value = mock_bound

        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="us-east-1",
            client=mock_client,
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hello"}])

        assert exc_info.value.provider == "bedrock"
        assert exc_info.value.is_retryable is False
        assert "AWS Bedrock account access restriction" in str(exc_info.value)
        assert "Model access" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_auth_failed_ap_south_2_translation(self) -> None:
        """Verify 403 Authentication failed in ap-south-2 informs the user to switch regions."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            side_effect=Exception(
                "An error occurred (AccessDeniedException) when calling the Converse operation: "
                "Authentication failed: Please make sure your API Key is valid."
            )
        )
        mock_client.bind.return_value = mock_bound

        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="ap-south-2",
            client=mock_client,
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete([{"role": "user", "content": "Hello"}])

        assert exc_info.value.provider == "bedrock"
        assert exc_info.value.is_retryable is False
        assert "Bedrock API keys (bearer tokens) are not supported in opt-in region 'ap-south-2'" in str(exc_info.value)
        assert "us-east-1" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bedrock_api_key_successful_complete(self) -> None:
        """Verify successful completion when using client configured with API key."""
        mock_client = MagicMock()
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="Here is your policy analysis with Bedrock API key.",
                usage_metadata={"input_tokens": 12, "output_tokens": 18, "total_tokens": 30},
            )
        )
        mock_client.bind.return_value = mock_bound

        provider = BedrockProvider(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name="us-east-1",
            bedrock_api_key="ABSK_valid_key",
            client=mock_client,
        )

        res = await provider.complete([{"role": "user", "content": "Analyze"}])
        assert res.provider == "bedrock"
        assert res.content == "Here is your policy analysis with Bedrock API key."
        assert res.usage["total_tokens"] == 30
