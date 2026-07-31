from __future__ import annotations

import json

import httpx
import pytest

from app.errors import (
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIRequestError,
    OpenAIServiceError,
)
from app.image_client import OpenAIImageClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,exception",
    [
        (401, OpenAIAuthenticationError),
        (429, OpenAIRateLimitError),
        (503, OpenAIServiceError),
        (400, OpenAIRequestError),
    ],
)
async def test_http_status_mapping(status, exception):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"x-request-id": "req-test"},
            json={"error": {"message": "simulated failure"}},
        )

    client = OpenAIImageClient(
        api_key="test",
        model="gpt-image-1",
        quality="medium",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(exception) as caught:
        await client.generate("album cover", 1)
    assert caught.value.request_id == "req-test"
