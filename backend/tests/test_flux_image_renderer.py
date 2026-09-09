from __future__ import annotations

import base64

import httpx
import pytest

from app.flux_image_client import CloudflareFluxImageClient


@pytest.mark.asyncio
async def test_flux_renderer_calls_workers_ai_and_decodes_image():
    image_bytes = b"fake-jpeg-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://api.cloudflare.com/client/v4/accounts/account-test/ai/run/"
            "@cf/black-forest-labs/flux-1-schnell"
        )
        assert request.headers["authorization"] == "Bearer token-test"
        payload = __import__("json").loads(request.content)
        assert "album cover" in payload["prompt"]
        assert payload["steps"] == 4
        return httpx.Response(
            200,
            headers={"cf-ray": "ray-test"},
            json={
                "success": True,
                "result": {"image": base64.b64encode(image_bytes).decode("ascii")},
            },
        )

    client = CloudflareFluxImageClient(
        account_id="account-test",
        api_token="token-test",
        model="@cf/black-forest-labs/flux-1-schnell",
        steps=4,
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await client.generate_exact("album cover", 1)
    assert result.content == image_bytes
    assert result.request_id == "ray-test"


def test_app_defaults_to_flux_renderer():
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        database_url="sqlite:///:memory:",
        cloudflare_account_id="account-test",
        cloudflare_api_token="token-test",
        allow_mock_images=False,
    )
    app = create_app(settings=settings)
    assert isinstance(app.state.generation_service.image_client, CloudflareFluxImageClient)
