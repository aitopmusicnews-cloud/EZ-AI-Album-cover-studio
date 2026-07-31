from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from .errors import (
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiServiceError,
)


@dataclass(slots=True)
class ConceptPlan:
    concepts: list[dict[str, str]]
    request_id: str | None = None


class GeminiCreativeDirector:
    """Uses Gemini only for cover-concept/prompt enhancement.

    OpenAI remains the image renderer. Keeping the creative-director provider separate
    reduces the tendency for one model family to both invent and render the same visual
    habits. If Gemini is not configured or temporarily unavailable, the service falls
    back to the local high-cardinality prompt planner; it never falls back to OpenAI for
    concept enhancement.
    """

    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-3.6-flash",
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

        previous = [item[-5000:] for item in (previous_prompts or [])[-3:]]
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
            "vocal_characteristics": signal.get("vocal_characteristics"),
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
You are an independent creative director for a professional record-label album-cover department.
Another company's image model will render your concepts. Your job is to invent exactly {count}
strong, commercially credible, mutually different cover ideas for ONE song.

Do not behave like a template engine. Start from the song's emotional story, lyrical clues and
musical character, then invent visual premises that could plausibly be pitched by different art
directors. Pairwise diversity is a hard requirement.

Rules:
- Every concept must differ in SUBJECT CATEGORY, SETTING CLASS, CAMERA LANGUAGE, DOMINANT SHAPE,
  VISUAL METAPHOR, and IMAGE-MAKING MEDIUM. Changing pose or color is not enough.
- For 4-5 concepts, include at least one concept with NO PERSON and at least one concept that is
  NOT conventional cinematic photography: e.g. tactile collage, painted/illustrated sleeve,
  screenprint, practical still-life, xerox/print construction, handmade object, or another coherent medium.
- No more than two concepts may center a visible human face.
- Do not default to classic cars, trucks, city streets, mansions, facades, skylines, motels,
  parking structures, gas stations or architecture-led scenes. Those require explicit lyric/theme support.
- Do not default to cracked statues, shattered faces, chrome masks, floating fragments,
  generic neon cyberpunk, smoke-filled portraits, or random abstract geometry.
- Do not force genre stereotypes. A rap song does not automatically need a car/city; a country song
  does not automatically need a truck/barn; an R&B song does not automatically need neon/bedroom imagery.
- Use one or two song-specific clues per concept and turn them into a coherent visual story.
- Typography is added later by the app. Do NOT render title, artist, logos or fake lettering.
- Reserve a deliberate typography-safe region and keep faces out of that region.
- If previous sets are supplied, avoid their central subject, environment, composition, medium,
  dominant prop and metaphor. A fresh set must feel like a new photo shoot/campaign, not a recolor.
- Make each image_prompt self-contained and ready for a separate image-generation API.
- Favor memorable real-world detail, gesture, texture and unexpected-but-relevant concepts over AI clichés.
""".strip()

        user_text = (
            "Design the next cover set from this JSON song context. Treat the provided base_brief as "
            "signal/context, not as a mandatory composition template. You are allowed to reject its visual "
            "suggestions when a more original song-specific concept is stronger.\n\n"
            + json.dumps(context, ensure_ascii=False)
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "system_instruction": system,
            "input": user_text,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeminiServiceError(f"Gemini creative-director request failed: {exc}") from exc

        request_id = (
            response.headers.get("x-request-id")
            or response.headers.get("x-goog-request-id")
            or response.headers.get("x-cloud-trace-context")
        )
        if response.status_code in {401, 403}:
            raise GeminiAuthenticationError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise GeminiRateLimitError(
                self._error_message(response), status_code=429, request_id=request_id
            )
        if response.status_code >= 500:
            raise GeminiServiceError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise GeminiRequestError(
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
            raise GeminiServiceError(
                f"Gemini returned an invalid concept plan: {exc}",
                request_id=request_id,
            ) from exc

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        # Some API surfaces expose a convenience output_text field. REST Interactions
        # responses expose model output in steps, so support both shapes.
        if isinstance(body.get("output_text"), str) and body["output_text"].strip():
            return body["output_text"]
        texts: list[str] = []
        for step in body.get("steps") or []:
            if step.get("type") != "model_output":
                continue
            for content in step.get("content") or []:
                if content.get("type") == "text" and content.get("text"):
                    texts.append(str(content["text"]))
        if texts:
            return "".join(texts)
        raise KeyError("No model-output text in Gemini Interactions response")

    @staticmethod
    def _validate_diversity(concepts: list[dict[str, str]]) -> None:
        # Reject an obviously repetitive plan before spending image-generation calls.
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
            if isinstance(error, dict):
                return str(error.get("message") or error)
            return str(error or payload)
        except Exception:
            return response.text[:500] or f"Gemini HTTP {response.status_code}"
