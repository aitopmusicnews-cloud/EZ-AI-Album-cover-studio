from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from io import BytesIO
import json
from typing import Any

import httpx
from PIL import Image, ImageStat

from .concept_ranking import _raise_for_status
from .platform_scoring import score_platforms


_SCORE_FIELDS = (
    "commercial_quality",
    "thumbnail_visibility",
    "professional_polish",
    "emotional_impact",
    "visual_storytelling",
    "genre_fit",
    "typography_quality",
    "originality",
    "platform_readiness",
)
_WEIGHTS = {
    "thumbnail_visibility": 0.25,
    "commercial_quality": 0.20,
    "professional_polish": 0.15,
    "visual_storytelling": 0.10,
    "emotional_impact": 0.10,
    "originality": 0.10,
    "genre_fit": 0.05,
    "typography_quality": 0.05,
}


@dataclass(frozen=True, slots=True)
class CoverInput:
    variation_id: str
    image_bytes: bytes
    concept_name: str = ""
    concept_prompt: str = ""


@dataclass(frozen=True, slots=True)
class CoverEvaluation:
    variation_id: str
    rank: int
    cover_score: float
    scores: dict[str, float]
    strengths: list[str]
    weaknesses: list[str]
    improvement_instructions: list[str]
    platform_scores: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class CoverCriticResult:
    evaluations: list[CoverEvaluation]
    winner_id: str
    runner_up_id: str | None
    request_id: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluations": [asdict(item) for item in self.evaluations],
            "winner_id": self.winner_id,
            "runner_up_id": self.runner_up_id,
            "request_id": self.request_id,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


class GeminiCoverCritic:
    endpoint_template = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 120,
        enabled: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.transport = transport

    async def evaluate(
        self,
        *,
        covers: list[CoverInput],
        signal: dict[str, Any],
        title: str | None,
        artist: str | None,
    ) -> CoverCriticResult:
        if not covers:
            raise ValueError("At least one cover is required")
        if not self.enabled or not self.api_key:
            return deterministic_critique(covers)

        parts: list[dict[str, Any]] = [
            {
                "text": (
                    "You are the final cover-art critic for a major record label. Compare every "
                    "completed, composited cover side by side. Score each from 1-10 for commercial "
                    "quality, thumbnail visibility at 100px, professional polish, emotional impact, "
                    "visual storytelling, genre fit, typography quality, originality, and platform "
                    "readiness. Weight thumbnail performance heavily. Return JSON only. Context: "
                    + json.dumps(
                        {
                            "title": title or "",
                            "artist": artist or "",
                            "genre": signal.get("inferred_genre"),
                            "mood": signal.get("mood"),
                            "covers": [
                                {
                                    "variation_id": cover.variation_id,
                                    "concept_name": cover.concept_name,
                                    "concept_prompt": cover.concept_prompt[:1500],
                                }
                                for cover in covers
                            ],
                        },
                        ensure_ascii=False,
                    )
                )
            }
        ]
        for cover in covers:
            parts.append({"text": f"COVER {cover.variation_id}"})
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(
                            _thumbnail_png(cover.image_bytes, 1000)
                        ).decode("ascii"),
                    }
                }
            )
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(
                            _thumbnail_png(cover.image_bytes, 100)
                        ).decode("ascii"),
                    }
                }
            )

        schema = _response_schema(len(covers))
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = self.endpoint_template.format(model=self.model)
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        request_id: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
            request_id = (
                response.headers.get("x-request-id")
                or response.headers.get("x-goog-request-id")
            )
            _raise_for_status(response, request_id)
            body = response.json()
            output_text = body["candidates"][0]["content"]["parts"][0]["text"]
            return _validate_response(json.loads(output_text), covers, request_id)
        except Exception as exc:
            fallback = deterministic_critique(covers)
            return CoverCriticResult(
                evaluations=fallback.evaluations,
                winner_id=fallback.winner_id,
                runner_up_id=fallback.runner_up_id,
                request_id=request_id,
                degraded=True,
                degraded_reason=f"{type(exc).__name__}: {exc}",
            )


def deterministic_critique(covers: list[CoverInput]) -> CoverCriticResult:
    raw: list[tuple[str, dict[str, float], list[str]]] = []
    for cover in covers:
        image = Image.open(BytesIO(cover.image_bytes)).convert("RGB")
        thumb = image.resize((100, 100), Image.Resampling.LANCZOS)
        stat = ImageStat.Stat(thumb)
        contrast = sum(stat.stddev) / (3 * 64)
        brightness = sum(stat.mean) / (3 * 255)
        edge_proxy = _edge_proxy(thumb)
        thumbnail = _clamp(5.0 + contrast * 3.2 + edge_proxy * 1.4 - abs(brightness - 0.5))
        polish = _clamp(5.8 + contrast * 1.6 - max(0.0, edge_proxy - 0.7))
        scores = {
            "commercial_quality": _clamp((thumbnail + polish) / 2),
            "thumbnail_visibility": thumbnail,
            "professional_polish": polish,
            "emotional_impact": _clamp(5.8 + contrast),
            "visual_storytelling": 6.0,
            "genre_fit": 6.0,
            "typography_quality": _clamp(5.5 + contrast * 1.2),
            "originality": 6.0,
            "platform_readiness": _clamp((thumbnail + polish) / 2),
        }
        weaknesses = []
        if thumbnail < 6:
            weaknesses.append("Improve focal separation and readability at 100px.")
        if contrast < 0.35:
            weaknesses.append("Increase tonal separation without crushing detail.")
        raw.append((cover.variation_id, scores, weaknesses))

    raw.sort(
        key=lambda item: (
            _weighted_total(item[1]),
            item[1]["thumbnail_visibility"],
            item[1]["commercial_quality"],
            item[1]["originality"],
        ),
        reverse=True,
    )
    evaluations: list[CoverEvaluation] = []
    for rank, (variation_id, scores, weaknesses) in enumerate(raw, start=1):
        platforms = {
            name: value.as_dict() for name, value in score_platforms(scores).items()
        }
        evaluations.append(
            CoverEvaluation(
                variation_id=variation_id,
                rank=rank,
                cover_score=_weighted_total(scores),
                scores=scores,
                strengths=[
                    field.replace("_", " ")
                    for field, value in scores.items()
                    if value >= 7.5
                ][:3],
                weaknesses=weaknesses,
                improvement_instructions=weaknesses or [
                    "Preserve the concept while exploring a stronger crop and title-safe contrast."
                ],
                platform_scores=platforms,
            )
        )
    return CoverCriticResult(
        evaluations=evaluations,
        winner_id=evaluations[0].variation_id,
        runner_up_id=evaluations[1].variation_id if len(evaluations) > 1 else None,
        degraded=True,
    )


def _validate_response(
    parsed: dict[str, Any], covers: list[CoverInput], request_id: str | None
) -> CoverCriticResult:
    expected = {cover.variation_id for cover in covers}
    rows = parsed["evaluations"]
    if len(rows) != len(covers):
        raise ValueError("Critic must evaluate every cover")
    ids = [str(row["variation_id"]) for row in rows]
    if set(ids) != expected or len(ids) != len(set(ids)):
        raise ValueError("Critic variation ids do not match the submitted covers")
    ranks = [int(row["rank"]) for row in rows]
    if sorted(ranks) != list(range(1, len(covers) + 1)):
        raise ValueError("Critic ranks must be unique and contiguous")

    evaluations: list[CoverEvaluation] = []
    for row in sorted(rows, key=lambda item: int(item["rank"])):
        scores = {field: float(row["scores"][field]) for field in _SCORE_FIELDS}
        if any(not 1 <= value <= 10 for value in scores.values()):
            raise ValueError("Cover scores must be between 1 and 10")
        platforms = {name: value.as_dict() for name, value in score_platforms(scores).items()}
        evaluations.append(
            CoverEvaluation(
                variation_id=str(row["variation_id"]),
                rank=int(row["rank"]),
                cover_score=_weighted_total(scores),
                scores=scores,
                strengths=[str(value) for value in row.get("strengths", [])],
                weaknesses=[str(value) for value in row.get("weaknesses", [])],
                improvement_instructions=[
                    str(value) for value in row.get("improvement_instructions", [])
                ],
                platform_scores=platforms,
            )
        )
    winner_id = evaluations[0].variation_id
    runner_up_id = evaluations[1].variation_id if len(evaluations) > 1 else None
    return CoverCriticResult(evaluations, winner_id, runner_up_id, request_id, False)


def _response_schema(count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "evaluations": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "variation_id": {"type": "string"},
                        "rank": {"type": "integer", "minimum": 1, "maximum": count},
                        "scores": {
                            "type": "object",
                            "properties": {
                                field: {"type": "number", "minimum": 1, "maximum": 10}
                                for field in _SCORE_FIELDS
                            },
                            "required": list(_SCORE_FIELDS),
                            "additionalProperties": False,
                        },
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "improvement_instructions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "variation_id",
                        "rank",
                        "scores",
                        "strengths",
                        "weaknesses",
                        "improvement_instructions",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["evaluations"],
        "additionalProperties": False,
    }


def _thumbnail_png(content: bytes, size: int) -> bytes:
    image = Image.open(BytesIO(content)).convert("RGB")
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _edge_proxy(image: Image.Image) -> float:
    gray = image.convert("L")
    pixels = gray.tobytes()
    width, height = gray.size
    if width < 2 or height < 2:
        return 0.0
    total = 0
    comparisons = 0
    for y in range(height - 1):
        row = y * width
        next_row = (y + 1) * width
        for x in range(width - 1):
            value = pixels[row + x]
            total += abs(value - pixels[row + x + 1])
            total += abs(value - pixels[next_row + x])
            comparisons += 2
    return min(1.0, total / max(comparisons * 64, 1))


def _weighted_total(scores: dict[str, float]) -> float:
    return round(sum(scores[field] * _WEIGHTS[field] for field in _WEIGHTS) * 10, 2)


def _clamp(value: float) -> float:
    return round(max(1.0, min(10.0, value)), 2)
