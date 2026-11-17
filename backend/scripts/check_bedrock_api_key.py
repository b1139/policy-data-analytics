"""Ad-hoc diagnostic script to test Amazon Bedrock access using BEDROCK_API_KEY."""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

# Add backend to path
sys.path.insert(0, os.path.abspath("backend"))

from app.core.config import settings
from app.llm.utils import mask_key


def test_direct_http_converse(region: str, model_id: str, token: str, header_mode: str = "Bearer"):
    url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if header_mode == "Bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif header_mode == "x-api-key":
        headers["x-api-key"] = token
    elif header_mode == "X-Amz-Bearer":
        headers["X-Amz-Bearer"] = token

    payload = {
        "messages": [{"role": "user", "content": [{"text": "Hello, answer with single word pong"}]}]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    print(f"\n--- Testing Direct HTTP Converse [{header_mode}] ---")
    print(f"URL: {url}")
    print(
        f"Headers: { {k: (mask_key(v) if 'auth' in k.lower() or 'key' in k.lower() or 'bearer' in k.lower() else v) for k, v in headers.items()} }"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            print(f"HTTP Status: {resp.status}")
            print(f"Response Body: {body[:300]}")
            return True, resp.status, body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP Error {e.code}: {e.reason}")
        print(f"Error Headers: {dict(e.headers)}")
        print(f"Error Body: {err_body}")
        return False, e.code, err_body
    except Exception as e:
        print(f"Unexpected Exception: {type(e).__name__}: {e}")
        return False, None, str(e)


def test_boto3_bearer(region: str, model_id: str, token: str):
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    print("\n--- Testing boto3 with AWS_BEARER_TOKEN_BEDROCK ---")
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token

    # Try standard client first
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        resp = client.converse(
            modelId=model_id, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )
        print("Boto3 Converse Success!")
        print("Response:", resp)
        return True, resp
    except Exception as e:
        print(f"Standard boto3 client converse failed: {type(e).__name__}: {e}")

    # Try with UNSIGNED config + before-sign header injection
    print("\n--- Testing boto3 with UNSIGNED + before-sign Authorization header ---")
    try:
        session = boto3.Session(region_name=region)
        cfg = Config(signature_version=UNSIGNED, connect_timeout=10, read_timeout=10)
        client = session.client("bedrock-runtime", region_name=region, config=cfg)

        def _inject(request, **_kwargs):
            request.headers["Authorization"] = f"Bearer {token}"

        client.meta.events.register("before-sign.bedrock-runtime.*", _inject)
        resp = client.converse(
            modelId=model_id, messages=[{"role": "user", "content": [{"text": "Hello"}]}]
        )
        print("Boto3 Injected Converse Success!")
        print("Response:", resp)
        return True, resp
    except Exception as e:
        print(f"Injected boto3 converse failed: {type(e).__name__}: {e}")
        return False, str(e)


async def test_bedrock_provider():
    from app.llm.bedrock_provider import BedrockProvider

    print("\n--- Testing app.llm.bedrock_provider.BedrockProvider ---")
    try:
        provider = BedrockProvider()
        print(
            f"Provider initialized: model={provider.model}, region={provider.region_name}, client={type(provider._client)}"
        )
        health = await provider.health_check()
        print(f"Health check result: {health}")
        resp = await provider.complete([{"role": "user", "content": "Ping"}], max_tokens=10)
        print(f"Complete result: {resp}")
        return True
    except Exception as e:
        import traceback

        print(f"BedrockProvider failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def main():
    token = settings.BEDROCK_API_KEY or os.environ.get("BEDROCK_API_KEY")
    region = settings.AWS_REGION or os.environ.get("AWS_REGION", "ap-south-2")
    model_id = settings.BEDROCK_MODEL_ID or os.environ.get(
        "BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"
    )

    print("=== Amazon Bedrock Diagnostic ===")
    print(f"Model ID: {model_id}")
    print(f"Region: {region}")
    print(f"API Key masked: {mask_key(token)}")
    print(f"API Key length: {len(token) if token else 0}")
    print(f"API Key prefix: {token[:4] if token else None}")

    if not token:
        print("ERROR: No BEDROCK_API_KEY found.")
        sys.exit(1)

    # 1. Direct HTTP tests on configured region & model
    for mode in ["Bearer", "x-api-key", "X-Amz-Bearer"]:
        test_direct_http_converse(region, model_id, token, header_mode=mode)

    # Also test us-east-1 to see if region is the only barrier
    if region != "us-east-1":
        print("\nChecking region us-east-1 as cross-check:")
        test_direct_http_converse("us-east-1", "amazon.nova-lite-v1:0", token, header_mode="Bearer")

    # 2. boto3 bearer test
    test_boto3_bearer(region, model_id, token)

    # 3. BedrockProvider test
    asyncio.run(test_bedrock_provider())


if __name__ == "__main__":
    main()
