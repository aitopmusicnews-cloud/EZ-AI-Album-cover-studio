import json

import httpx
import pytest

from app.creative_director import GeminiCreativeDirector
from app.errors import GeminiAuthenticationError, GeminiRateLimitError, GeminiServiceError


def _concepts(count: int) -> list[dict[str, str]]:
    return [
        {
            "name": f"C{i}",
            "subject": f"subject {i}",
            "setting": f"setting {i}",
            "action_or_symbol": f"symbol {i}",
            "camera": f"camera {i}",
            "medium": f"medium {i}",
            "palette": f"palette {i}",
            "typography_zone": f"zone {i}",
            "image_prompt": f"image prompt {i}",
        }
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_gemini_creative_director_uses_interactions_structured_output_and_parses_plan():
    concepts = _concepts(3)

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "test-gemini-key"
        assert payload["model"] == "gemini-3.6-flash"
        assert payload["response_format"]["type"] == "text"
        assert payload["response_format"]["mime_type"] == "application/json"
        assert payload["response_format"]["schema"]["type"] == "object"
        assert "previous_sets_to_avoid" in payload["input"]
        assert "independent creative director" in payload["system_instruction"]
        return httpx.Response(
            200,
            headers={"x-goog-request-id": "gem-plan"},
            json={
                "id": "int-test",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "status": "done",
                        "content": [
                            {"type": "text", "text": json.dumps({"concepts": concepts})}
                        ],
                    }
                ],
            },
        )

    director = GeminiCreativeDirector(
        api_key="test-gemini-key",
        model="gemini-3.6-flash",
        transport=httpx.MockTransport(handler),
    )
    plan = await director.plan(
        base_brief="brief",
        signal={"mood": {"label": "dark"}, "keywords": ["rain"]},
        count=3,
        creative_seed="seed",
        title="Title",
        artist="Artist",
        previous_prompts=["old concept"],
    )
    assert len(plan.concepts) == 3
    assert plan.request_id == "gem-plan"


@pytest.mark.asyncio
async def test_gemini_without_key_returns_empty_plan_for_local_fallback():
    director = GeminiCreativeDirector(api_key=None)
    plan = await director.plan(
        base_brief="brief",
        signal={},
        count=3,
        creative_seed="seed",
        title=None,
        artist=None,
    )
    assert plan.concepts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,error_type",
    [
        (401, GeminiAuthenticationError),
        (429, GeminiRateLimitError),
        (503, GeminiServiceError),
    ],
)
async def test_gemini_errors_are_classified(status, error_type):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "provider error"}})

    director = GeminiCreativeDirector(
        api_key="test-gemini-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(error_type):
        await director.plan(
            base_brief="brief",
            signal={},
            count=3,
            creative_seed="seed",
            title=None,
            artist=None,
        )
