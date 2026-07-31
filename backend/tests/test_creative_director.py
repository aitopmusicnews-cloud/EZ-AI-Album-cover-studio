import json

import httpx
import pytest

from app.creative_director import OpenAICreativeDirector


@pytest.mark.asyncio
async def test_creative_director_uses_structured_responses_api_and_parses_plan():
    concepts = [
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
        for i in range(3)
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert payload["model"] == "gpt-5.6-luna"
        assert payload["text"]["format"]["type"] == "json_schema"
        assert "previous_sets_to_avoid" in payload["input"][1]["content"]
        return httpx.Response(
            200,
            headers={"x-request-id": "req-plan"},
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"concepts": concepts})}
                        ],
                    }
                ]
            },
        )

    director = OpenAICreativeDirector(
        api_key="test-key",
        model="gpt-5.6-luna",
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
    assert plan.request_id == "req-plan"
