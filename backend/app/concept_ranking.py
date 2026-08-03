from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

import httpx

from .errors import (
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiServiceError,
)


_SCORE_FIELDS = (
    "commercial_appeal",
    "originality",
    "thumbnail_impact",
    "emotional_impact",
    "genre_fit",
    "streaming_platform_viability",
    "visual_clarity",
)
_WEIGHTS = {
    "commercial_appeal": 0.20,
    "originality": 0.20,
    "thumbnail_impact": 0.20,
    "emotional_impact": 0.15,
    "genre_fit": 0.10,
    "streaming_platform_viability": 0.10,
    "visual_clarity": 0.05,
}


@dataclass(frozen=True, slots=True)
class RankedConcept:
    concept_id: str
    rank: int
    total_score: float
    scores: dict[str, float]
    strengths: list[str]
    risks: list[str]
    rationale: str


@dataclass(frozen=True, slots=True)
class ConceptRankingResult:
    ranked_concepts: list[RankedConcept]
    selected_concept_ids: list[str]
    request_id: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ranked_concepts": [asdict(item) for item in self.ranked_concepts],
            "selected_concept_ids": self.selected_concept_ids,
            "request_id": self.request_id,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


class GeminiConceptRanker:
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 90,
        enabled: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.transport = transport

    async def rank(
        self,
        *,
        concepts: list[dict[str, Any]],
        signal: dict[str, Any],
        title: str | None,
        artist: str | None,
        selected_count: int = 2,
    ) -> ConceptRankingResult:
        normalized = _normalize_concepts(concepts)
        if not self.enabled or not self.api_key:
            return deterministic_rank(normalized, selected_count=selected_count, degraded=True)

        schema = _response_schema(len(normalized), selected_count)
        context = {
            "release_title": title or "",
            "artist": artist or "",
            "genre": signal.get("inferred_genre"),
            "mood": signal.get("mood"),
            "themes": signal.get("themes", [])[:8],
            "concepts": normalized,
        }
        payload = {
            "model": self.model,
            "system_instruction": (
                "You are a senior creative director at a major record label. Score every concept "
                "independently from 1-10 for commercial appeal, originality, thumbnail impact, "
                "emotional impact, genre fit, streaming-platform viability, and visual clarity. "
                "Penalize generic AI imagery, genre stereotypes, weak focal points, clutter, and "
                "concepts that collapse at 100px. Return ranked JSON only. Do not rewrite concepts."
            ),
            "input": json.dumps(context, ensure_ascii=False),
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        request_id: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
            request_id = (
                response.headers.get("x-request-id")
                or response.headers.get("x-goog-request-id")
                or response.headers.get("x-cloud-trace-context")
            )
            _raise_for_status(response, request_id)
            output_text = _extract_output_text(response.json())
            parsed = json.loads(output_text)
            return _validate_response(parsed, normalized, selected_count, request_id)
        except Exception as exc:
            fallback = deterministic_rank(
                normalized,
                selected_count=selected_count,
                degraded=True,
            )
            return ConceptRankingResult(
                ranked_concepts=fallback.ranked_concepts,
                selected_concept_ids=fallback.selected_concept_ids,
                request_id=request_id,
                degraded=True,
                degraded_reason=f"{type(exc).__name__}: {exc}",
            )


def deterministic_rank(
    concepts: list[dict[str, Any]], *, selected_count: int = 2, degraded: bool = True
) -> ConceptRankingResult:
    normalized = _normalize_concepts(concepts)
    evaluated: list[tuple[str, dict[str, float], str]] = []
    for concept in normalized:
        concept_id = concept["id"]
        text = " ".join(str(concept.get(field, "")) for field in concept if field != "id")
        tokens = [token.strip(".,:;!?()[]{}").lower() for token in text.split() if token.strip()]
        unique_ratio = len(set(tokens)) / max(len(tokens), 1)
        clarity = min(10.0, 4.5 + min(len(text), 900) / 180)
        stable = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        jitter = (stable % 151) / 100 - 0.75
        scores = {
            "commercial_appeal": _clamp(6.2 + clarity * 0.22 + jitter),
            "originality": _clamp(4.2 + unique_ratio * 5.2 + jitter / 2),
            "thumbnail_impact": _clamp(5.5 + _focus_bonus(concept) + jitter / 3),
            "emotional_impact": _clamp(5.4 + _story_bonus(concept) + jitter / 3),
            "genre_fit": _clamp(6.0 + jitter / 2),
            "streaming_platform_viability": _clamp(5.7 + _focus_bonus(concept) * 0.7),
            "visual_clarity": _clamp(clarity),
        }
        rationale = "Deterministic fallback based on specificity, focus, story detail, and prompt clarity."
        evaluated.append((concept_id, scores, rationale))

    evaluated.sort(key=lambda item: _weighted_total(item[1]), reverse=True)
    ranked = [
        RankedConcept(
            concept_id=concept_id,
            rank=index,
            total_score=_weighted_total(scores),
            scores=scores,
            strengths=_strengths(scores),
            risks=_risks(scores),
            rationale=rationale,
        )
        for index, (concept_id, scores, rationale) in enumerate(evaluated, start=1)
    ]
    return ConceptRankingResult(
        ranked_concepts=ranked,
        selected_concept_ids=[item.concept_id for item in ranked[:selected_count]],
        degraded=degraded,
    )


def _normalize_concepts(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not concepts:
        raise ValueError("At least one concept is required")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, concept in enumerate(concepts, start=1):
        concept_id = str(concept.get("id") or concept.get("concept_id") or f"concept-{index}")
        if concept_id in seen:
            raise ValueError(f"Duplicate concept id: {concept_id}")
        seen.add(concept_id)
        normalized.append({"id": concept_id, **{k: v for k, v in concept.items() if k not in {"id", "concept_id"}}})
    return normalized


def _response_schema(count: int, selected_count: int) -> dict[str, Any]:
    score_properties = {field: {"type": "number", "minimum": 1, "maximum": 10} for field in _SCORE_FIELDS}
    return {
        "type": "object",
        "properties": {
            "ranked_concepts": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "concept_id": {"type": "string"},
                        "rank": {"type": "integer", "minimum": 1, "maximum": count},
                        "scores": {
                            "type": "object",
                            "properties": score_properties,
                            "required": list(_SCORE_FIELDS),
                            "additionalProperties": False,
                        },
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": "string"},
                    },
                    "required": ["concept_id", "rank", "scores", "strengths", "risks", "rationale"],
                    "additionalProperties": False,
                },
            },
            "selected_concept_ids": {
                "type": "array",
                "minItems": selected_count,
                "maxItems": selected_count,
                "items": {"type": "string"},
            },
        },
        "required": ["ranked_concepts", "selected_concept_ids"],
        "additionalProperties": False,
    }


def _validate_response(
    parsed: dict[str, Any],
    concepts: list[dict[str, Any]],
    selected_count: int,
    request_id: str | None,
) -> ConceptRankingResult:
    expected_ids = {item["id"] for item in concepts}
    raw_ranked = parsed["ranked_concepts"]
    if len(raw_ranked) != len(concepts):
        raise ValueError("Ranking must contain every concept exactly once")
    ids = [str(item["concept_id"]) for item in raw_ranked]
    if set(ids) != expected_ids or len(ids) != len(set(ids)):
        raise ValueError("Ranking concept ids do not match the submitted concepts")
    ranks = [int(item["rank"]) for item in raw_ranked]
    if sorted(ranks) != list(range(1, len(concepts) + 1)):
        raise ValueError("Ranks must be unique and contiguous")

    ranked: list[RankedConcept] = []
    for item in sorted(raw_ranked, key=lambda row: int(row["rank"])):
        scores = {field: float(item["scores"][field]) for field in _SCORE_FIELDS}
        if any(not 1 <= value <= 10 for value in scores.values()):
            raise ValueError("Concept scores must be between 1 and 10")
        ranked.append(
            RankedConcept(
                concept_id=str(item["concept_id"]),
                rank=int(item["rank"]),
                total_score=_weighted_total(scores),
                scores=scores,
                strengths=[str(value) for value in item.get("strengths", [])],
                risks=[str(value) for value in item.get("risks", [])],
                rationale=str(item.get("rationale", "")),
            )
        )
    selected = [str(value) for value in parsed["selected_concept_ids"]]
    expected_selected = [item.concept_id for item in ranked[:selected_count]]
    if selected != expected_selected:
        selected = expected_selected
    return ConceptRankingResult(ranked, selected, request_id=request_id, degraded=False)


def _weighted_total(scores: dict[str, float]) -> float:
    return round(sum(scores[field] * _WEIGHTS[field] for field in _SCORE_FIELDS) * 10, 2)


def _clamp(value: float) -> float:
    return round(max(1.0, min(10.0, value)), 2)


def _focus_bonus(concept: dict[str, Any]) -> float:
    text = f"{concept.get('subject', '')} {concept.get('action_or_symbol', '')}".lower()
    penalties = sum(word in text for word in ("many", "crowd of", "complex", "multiple scenes"))
    bonuses = sum(word in text for word in ("one ", "single", "silhouette", "icon", "bold"))
    return max(-1.0, min(1.8, bonuses * 0.45 - penalties * 0.55))


def _story_bonus(concept: dict[str, Any]) -> float:
    text = f"{concept.get('action_or_symbol', '')} {concept.get('setting', '')}".lower()
    return min(1.8, len({word for word in text.split() if len(word) > 6}) / 8)


def _strengths(scores: dict[str, float]) -> list[str]:
    return [field.replace("_", " ") for field, value in scores.items() if value >= 7.5][:3]


def _risks(scores: dict[str, float]) -> list[str]:
    return [field.replace("_", " ") for field, value in scores.items() if value < 6.0][:3]


def _extract_output_text(body: dict[str, Any]) -> str:
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
    raise KeyError("No model-output text in Gemini response")


def _raise_for_status(response: httpx.Response, request_id: str | None) -> None:
    if response.status_code < 400:
        return
    try:
        payload = response.json()
        error = payload.get("error", {})
        message = str(error.get("message") if isinstance(error, dict) else error or payload)
    except Exception:
        message = response.text[:500] or f"Gemini HTTP {response.status_code}"
    if response.status_code in {401, 403}:
        raise GeminiAuthenticationError(message, status_code=response.status_code, request_id=request_id)
    if response.status_code == 429:
        raise GeminiRateLimitError(message, status_code=429, request_id=request_id)
    if response.status_code >= 500:
        raise GeminiServiceError(message, status_code=response.status_code, request_id=request_id)
    raise GeminiRequestError(message, status_code=response.status_code, request_id=request_id)
