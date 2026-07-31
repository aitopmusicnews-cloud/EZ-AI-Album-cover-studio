from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from .errors import (
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIRequestError,
    OpenAIServiceError,
)


@dataclass(slots=True)
class ConceptPlan:
    concepts: list[dict[str, str]]
    request_id: str | None = None


class OpenAICreativeDirector:
    """Creates song-specific, mutually distinct cover concepts before image generation.

    The image model is excellent at rendering a concept but can converge on a house
    style when every request is built from the same prompt template.  This planner
    inserts a separate creative-director pass that invents the actual visual premises
    and explicitly compares them with previous sets for the same song.
    """

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-5.6-luna",
        timeout_seconds: float = 90,
        enabled: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.transport = transport

    async def plan(
        self,
        *,
        base_brief: str,
        signal: dict[str, Any],
        count: int,
        creative_seed: str,
        title: str | None,
        artist: str | None,
        previous_prompts: list[str] | None = None,
    ) -> ConceptPlan:
        if not self.enabled or not self.api_key:
            return ConceptPlan([])

        previous = [item[-4500:] for item in (previous_prompts or [])[-3:]]
        context = {
            "release_title": title or "",
            "artist": artist or "",
            "creative_batch_id": creative_seed[-48:],
            "requested_concepts": count,
            "mood": signal.get("mood"),
            "genre": signal.get("inferred_genre"),
            "themes": signal.get("themes", [])[:8],
            "imagery": signal.get("imagery", [])[:12],
            "keywords": signal.get("keywords", [])[:14],
            "tempo_bpm": signal.get("tempo_bpm"),
            "key": signal.get("key"),
            "scale": signal.get("scale"),
            "style_tags": signal.get("style_tags", [])[:8],
            "base_brief": base_brief,
            "previous_sets_to_avoid": previous,
        }

        schema = {
            "type": "object",
            "properties": {
                "concepts": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "subject": {"type": "string"},
                            "setting": {"type": "string"},
                            "action_or_symbol": {"type": "string"},
                            "camera": {"type": "string"},
                            "medium": {"type": "string"},
                            "palette": {"type": "string"},
                            "typography_zone": {"type": "string"},
                            "image_prompt": {"type": "string"},
                        },
                        "required": [
                            "name",
                            "subject",
                            "setting",
                            "action_or_symbol",
                            "camera",
                            "medium",
                            "palette",
                            "typography_zone",
                            "image_prompt",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["concepts"],
            "additionalProperties": False,
        }

        system = f"""
You are the creative director for a professional record-label album-cover department.
Create exactly {count} genuinely different cover concepts for ONE song.

The failure mode you must prevent is repetition. Do not make five versions of the
same portrait, street, car, building, room, color palette, camera angle, or visual
metaphor. Pairwise diversity is a hard requirement.

Rules:
- Every concept must have a different SUBJECT CATEGORY, SETTING CLASS, CAMERA LANGUAGE,
  DOMINANT SHAPE, and IMAGE-MAKING MEDIUM from every other concept.
- For 4-5 concepts, include at least one concept with NO PERSON and at least one concept
  that is NOT conventional cinematic photography (for example tactile collage,
  screenprint, painted/illustrated sleeve, xerox/print construction, or practical still-life).
- No more than two concepts may center a visible human face.
- Do not use transportation, classic cars, trucks, mansions, skylines, facades,
  parking lots, motels, gas stations, or generic city streets unless those ideas are
  explicitly supported by the supplied song imagery/keywords. Genre does not earn a prop.
- Do not use cracked statues, shattered faces, chrome masks, floating fragments,
  generic neon cyberpunk, or random abstract geometry as automatic AI-art shorthand.
- Use only one or two song-specific lyrical clues in each concept; invent a coherent
  visual story rather than illustrating a keyword checklist.
- Typography will be added later. Leave a deliberate text-safe area and never place a
  face there. Do not ask the image model to render the title or artist name.
- Covers must feel commercially credible and visually memorable at thumbnail size.
- If previous sets are supplied, avoid their subject, environment, composition,
  medium, and central metaphor. Fresh means genuinely new, not a recolor.
- The image_prompt field must be a complete, self-contained prompt for an image model.
""".strip()

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": "Design the next cover set from this JSON context:\n"
                    + json.dumps(context, ensure_ascii=False),
                },
            ],
            "reasoning": {"effort": "low"},
            "max_output_tokens": 2600,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "album_cover_concept_plan",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise OpenAIServiceError(f"Creative-director request failed: {exc}") from exc

        request_id = response.headers.get("x-request-id")
        if response.status_code in {401, 403}:
            raise OpenAIAuthenticationError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise OpenAIRateLimitError(
                self._error_message(response), status_code=429, request_id=request_id
            )
        if response.status_code >= 500:
            raise OpenAIServiceError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise OpenAIRequestError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )

        try:
            body = response.json()
            text = self._extract_output_text(body)
            parsed = json.loads(text)
            concepts = parsed["concepts"]
            if len(concepts) != count:
                raise ValueError(f"expected {count} concepts, got {len(concepts)}")
            self._validate_diversity(concepts)
            return ConceptPlan(concepts=concepts, request_id=request_id)
        except Exception as exc:
            raise OpenAIServiceError(
                f"Creative director returned an invalid concept plan: {exc}",
                request_id=request_id,
            ) from exc

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        if isinstance(body.get("output_text"), str) and body["output_text"].strip():
            return body["output_text"]
        for item in body.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
        raise KeyError("No output_text in Responses API payload")

    @staticmethod
    def _validate_diversity(concepts: list[dict[str, str]]) -> None:
        # Reject obviously duplicated plans before spending image-generation calls.
        for field in ("subject", "setting", "camera", "medium"):
            normalized = [" ".join(str(c[field]).lower().split()) for c in concepts]
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"concept plan repeats {field}")
        prompts = [" ".join(str(c["image_prompt"]).lower().split()) for c in concepts]
        if len(set(prompts)) != len(prompts):
            raise ValueError("concept plan repeats image prompts")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {})
            return str(error.get("message") or payload)
        except Exception:
            return response.text[:500] or f"OpenAI HTTP {response.status_code}"
