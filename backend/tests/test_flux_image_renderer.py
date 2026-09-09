from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from app import image_client


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
MODEL = "@cf/black-forest-labs/flux-1-schnell"


def test_default_album_cover_renderer_is_cloudflare_flux_only():
    main_source = (APP_ROOT / "main.py").read_text(encoding="utf-8")
    config_source = (APP_ROOT / "config.py").read_text(encoding="utf-8")
    client_source = (APP_ROOT / "image_client.py").read_text(encoding="utf-8")

    assert hasattr(image_client, "CloudflareFluxImageClient")
    assert "CloudflareFluxImageClient" in main_source
    assert '"cloudflare_flux_images"' in main_source
    assert "CLOUDFLARE_ACCOUNT_ID" in config_source
    assert "CLOUDFLARE_API_TOKEN" in config_source
    assert "CLOUDFLARE_FLUX_MODEL" in config_source
    assert "pollinations" not in main_source.lower()
    assert "pollinations" not in config_source.lower()
    assert "pollinations" not in client_source.lower()


@pytest.mark.asyncio
async def test_cloudflare_flux_client_calls_workers_ai_schnell():
    captured: dict[str, object] = {}
    image_bytes = b"cloudflare-flux-jpeg"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            headers={"cf-ray": "workers-ai-request"},
            json={
                "result": {"image": base64.b64encode(image_bytes).decode("ascii")},
                "success": True,
                "errors": [],
                "messages": [],
            },
        )

    client = image_client.CloudflareFluxImageClient(
        account_id="account-test",
        api_token="cloudflare-test-token",
        model=MODEL,
        steps=4,
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate_exact("professional album cover", 1)

    assert result.content == image_bytes
    assert result.request_id == "workers-ai-request"
    assert captured["authorization"] == "Bearer cloudflare-test-token"
    assert captured["content_type"] == "application/json"
    assert captured["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/account-test/ai/run/"
        "@cf/black-forest-labs/flux-1-schnell"
    )
    assert captured["body"] == {
        "prompt": "professional album cover",
        "steps": 4,
    }
