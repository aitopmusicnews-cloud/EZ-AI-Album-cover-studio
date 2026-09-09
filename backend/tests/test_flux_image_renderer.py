from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from app import image_client


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_default_album_cover_renderer_is_flux_only():
    main_source = (APP_ROOT / "main.py").read_text(encoding="utf-8")
    config_source = (APP_ROOT / "config.py").read_text(encoding="utf-8")

    assert hasattr(image_client, "FluxImageClient"), "FLUX image renderer is not implemented yet"
    assert "FluxImageClient" in main_source
    assert "GeminiImageClient" not in main_source
    assert '"gemini_images"' not in main_source
    assert '"flux_images"' in main_source
    assert "POLLINATIONS_API_KEY" in config_source
    assert "FLUX_IMAGE_MODEL" in config_source


@pytest.mark.asyncio
async def test_flux_image_client_generates_square_image_through_pollinations():
    client_class = getattr(image_client, "FluxImageClient", None)
    assert client_class is not None, "FLUX image renderer is not implemented yet"

    captured: dict[str, object] = {}
    image_bytes = b"flux-image-png"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            headers={"x-request-id": "flux-image-request"},
            json={
                "created": 1,
                "data": [
                    {"b64_json": base64.b64encode(image_bytes).decode("ascii")}
                ],
            },
        )

    client = client_class(
        api_key="pollinations-test-key",
        model="flux",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate_exact("professional album cover", 1)

    assert result.content == image_bytes
    assert result.request_id == "flux-image-request"
    assert captured["authorization"] == "Bearer pollinations-test-key"
    assert captured["url"] == "https://gen.pollinations.ai/v1/images/generations"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body == {
        "model": "flux",
        "prompt": "professional album cover",
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }
