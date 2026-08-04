from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Generation, VariationSet


TERMINAL_SUCCESS = {"complete", "partial"}
TERMINAL_FAILURE = {"analysis_failed", "image_failed"}


def collection_metrics(db: Session, collection_id: str) -> dict[str, Any]:
    generations = list(
        db.scalars(
            select(Generation)
            .options(
                selectinload(Generation.variation_sets).selectinload(VariationSet.variations),
                selectinload(Generation.audit_events),
            )
            .where(Generation.collection_id == collection_id)
            .order_by(Generation.version)
        )
    )
    return summarize_collection(collection_id, generations)


def summarize_collection(
    collection_id: str, generations: Iterable[Generation]
) -> dict[str, Any]:
    versions = list(generations)
    sets = [item for generation in versions for item in generation.variation_sets]
    covers = [variation for item in sets for variation in item.variations]
    scored = [variation for variation in covers if variation.cover_score is not None]

    status_counts = Counter(str(generation.status) for generation in versions)
    set_status_counts = Counter(str(item.status) for item in sets)
    successful_versions = sum(
        count for status, count in status_counts.items() if status in TERMINAL_SUCCESS
    )
    failed_versions = sum(
        count for status, count in status_counts.items() if status in TERMINAL_FAILURE
    )
    completed_critics = sum(item.critic_status in {"complete", "degraded"} for item in sets)

    platform_values: dict[str, list[float]] = defaultdict(list)
    for variation in covers:
        for platform, payload in (variation.platform_scores_json or {}).items():
            value = payload.get("score") if isinstance(payload, dict) else payload
            numeric = _number(value)
            if numeric is not None:
                platform_values[str(platform)].append(numeric)

    audit_events = [event for generation in versions for event in generation.audit_events]
    retries = sum(int(getattr(event, "attempt", 1) or 1) > 1 for event in audit_events)
    failed_steps = sum(str(getattr(event, "outcome", "")) == "failed" for event in audit_events)
    cache_hits = sum(
        str(getattr(event, "step", "")) == "cache_lookup"
        and str(getattr(event, "outcome", "")) == "hit"
        for event in audit_events
    )

    quality_trend = []
    for generation in versions:
        for item in generation.variation_sets:
            item_scores = [
                float(variation.cover_score)
                for variation in item.variations
                if variation.cover_score is not None
            ]
            winner = next(
                (
                    variation
                    for variation in item.variations
                    if variation.id == item.ai_winner_variation_id
                    or variation.selection_tier == "winner"
                ),
                None,
            )
            quality_trend.append(
                {
                    "version": generation.version,
                    "set_number": item.set_number,
                    "average_score": _round_mean(item_scores),
                    "winner_score": (
                        round(float(winner.cover_score), 2)
                        if winner is not None and winner.cover_score is not None
                        else None
                    ),
                    "created_at": item.created_at,
                }
            )

    latest_update = max(
        (generation.updated_at for generation in versions if generation.updated_at),
        default=None,
    )
    release_ready = sum(
        (variation.commercial_score or 0) >= 80 and (variation.cover_score or 0) >= 75
        for variation in covers
    )

    return {
        "collection_id": collection_id,
        "versions": len(versions),
        "variation_sets": len(sets),
        "covers_generated": len(covers),
        "scored_covers": len(scored),
        "selected_covers": sum(bool(generation.selected_variation_id) for generation in versions),
        "successful_versions": successful_versions,
        "failed_versions": failed_versions,
        "success_rate": _percent(successful_versions, len(versions)),
        "critic_completion_rate": _percent(completed_critics, len(sets)),
        "average_cover_score": _round_mean(
            float(variation.cover_score) for variation in scored
        ),
        "average_thumbnail_score": _round_mean(
            float(variation.thumbnail_score)
            for variation in covers
            if variation.thumbnail_score is not None
        ),
        "average_commercial_score": _round_mean(
            float(variation.commercial_score)
            for variation in covers
            if variation.commercial_score is not None
        ),
        "best_cover_score": max(
            (float(variation.cover_score) for variation in scored), default=None
        ),
        "release_ready_covers": release_ready,
        "retries": retries,
        "failed_steps": failed_steps,
        "cache_hits": cache_hits,
        "status_counts": dict(sorted(status_counts.items())),
        "set_status_counts": dict(sorted(set_status_counts.items())),
        "platform_averages": {
            platform: _round_mean(values) for platform, values in sorted(platform_values.items())
        },
        "quality_trend": quality_trend[-10:],
        "latest_update": latest_update,
    }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return round(mean(items), 2) if items else None


def _percent(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0.0
