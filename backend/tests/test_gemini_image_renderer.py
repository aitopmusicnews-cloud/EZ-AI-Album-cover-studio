from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from app import image_client


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_default_album_cover_renderer_is_gemini_only():
    main_source = (APP_ROOT / "main.py").read_text(encoding="utf-8")
    config_source = (APP_ROOT / "config.py").read_text(encoding="utf-8")

    assert hasattr(image_client, "GeminiImageClient"), "Gemini image renderer is not implemented yet"
    assert "OpenAIImageClient" not in main_source
    assert '"openai_images"' not in main_source
    assert '"gemini_images"' in main_source
    assert "GEMINI_IMAGE_MODEL" in config_source


@pytest.mark.asyncio
async def test_gemini_image_client_generates_square_image_from_gemini_api():
    client_class = getattr(image_client, "GeminiImageClient", None)
    assert client_class is not None, "Gemini image renderer is not implemented yet"

    captured: dict[str, object] = {}
    image_bytes = b"gemini-image-png"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            headers={"x-goog-request-id": "gemini-image-request"},
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = client_class(
        api_key="gemini-test-key",
        model="gemini-3.1-flash-image",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate_exact("professional album cover", 1)

    assert result.content == image_bytes
    assert result.request_id == "gemini-image-request"
    assert captured["api_key"] == "gemini-test-key"
    assert str(captured["url"]).endswith(
        "/v1/models/gemini-3.1-flash-image:generateContent"
    )
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert body["generationConfig"]["responseFormat"]["image"] == {
        "aspectRatio": "1:1",
        "imageSize": "1K",
    }
