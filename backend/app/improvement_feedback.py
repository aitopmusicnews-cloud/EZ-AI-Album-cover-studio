from __future__ import annotations

from typing import Any


def build_improvement_context(variation_set: Any) -> tuple[str, str | None]:
    """Build a focused refinement brief from the latest set's strongest cover.

    The function deliberately accepts simple attribute-based objects so it can be
    unit-tested without a database session and reused by future pipeline workers.
    """
    variations = list(getattr(variation_set, "variations", None) or [])
    if not variations:
        return (
            "Create a stronger follow-up with clearer hierarchy, better thumbnail recognition, "
            "more disciplined typography, and a more premium commercial finish.",
            None,
        )

    winner_id = getattr(variation_set, "ai_winner_variation_id", None)
    winner = next((item for item in variations if getattr(item, "id", None) == winner_id), None)
    if winner is None:
        winner = min(
            variations,
            key=lambda item: (
                getattr(item, "rank", None) is None,
                getattr(item, "rank", None) or 10_000,
                -(float(getattr(item, "cover_score", None) or 0.0)),
            ),
        )

    concepts = {
        getattr(item, "id", None): item
        for item in (getattr(variation_set, "concepts", None) or [])
    }
    concept = concepts.get(getattr(winner, "concept_candidate_id", None))
    concept_name = getattr(concept, "name", None)
    feedback = getattr(winner, "cover_feedback_json", None) or {}
    scores = getattr(winner, "critic_scores_json", None) or {}

    strengths = _clean_list(feedback.get("strengths"))
    weaknesses = _clean_list(feedback.get("weaknesses"))
    instructions = _clean_list(feedback.get("improvement_instructions"))
    weak_dimensions = _lowest_dimensions(scores)

    lines = ["Create a materially improved follow-up to the previous AI winner."]
    if concept_name:
        lines.append(f"Reference concept: {concept_name}.")
    if strengths:
        lines.append("Preserve these strengths: " + "; ".join(strengths) + ".")
    if weaknesses:
        lines.append("Correct these weaknesses: " + "; ".join(weaknesses) + ".")
    if instructions:
        lines.append("Required refinements: " + "; ".join(instructions) + ".")
    if weak_dimensions:
        lines.append("Raise these lowest-scoring dimensions: " + ", ".join(weak_dimensions) + ".")
    lines.append(
        "Keep the emotional truth and strongest visual hook, but do not duplicate the exact subject, "
        "camera angle, composition, prop arrangement, or typography placement. Produce genuinely new, "
        "more release-ready executions with stronger small-format recognition."
    )
    return "\n".join(lines), getattr(winner, "id", None)


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]


def _lowest_dimensions(scores: dict[str, Any]) -> list[str]:
    labels = {
        "commercial_quality": "commercial quality",
        "professional_polish": "professional polish",
        "originality": "originality",
        "visual_storytelling": "visual storytelling",
        "thumbnail_visibility": "thumbnail visibility",
        "typography_quality": "typography quality",
        "genre_fit": "genre fit",
        "emotional_alignment": "emotional alignment",
    }
    numeric: list[tuple[float, str]] = []
    for key, label in labels.items():
        try:
            numeric.append((float(scores[key]), label))
        except (KeyError, TypeError, ValueError):
            continue
    numeric.sort()
    return [label for score, label in numeric if score < 7.5][:3]
