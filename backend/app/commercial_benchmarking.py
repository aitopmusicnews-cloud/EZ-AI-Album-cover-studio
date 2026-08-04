from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True, slots=True)
class CommercialBenchmark:
    rubric: str
    score: float
    grade: str
    percentile_band: str
    release_readiness: str
    target_score: float
    passed_gates: list[str]
    improvement_gaps: list[str]
    next_action: str
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def benchmark_cover(
    *,
    critic_scores: dict[str, Any] | None,
    platform_scores: dict[str, Any] | None,
    market_lane: str | None = None,
) -> dict[str, Any]:
    """Benchmark a cover against an internal major-label release rubric.

    This is a consistent quality benchmark, not a claim about live charts, sales,
    streaming performance, or a proprietary competitor dataset.
    """
    scores = critic_scores or {}
    platforms = platform_scores or {}

    dimensions = {
        "commercial quality": _score(scores, "commercial_quality", 5.0),
        "professional polish": _score(scores, "professional_polish", 5.0),
        "thumbnail visibility": _score(scores, "thumbnail_visibility", 5.0),
        "typography quality": _score(scores, "typography_quality", 5.0),
        "originality": _score(scores, "originality", 5.0),
        "visual storytelling": _score(scores, "visual_storytelling", 5.0),
    }
    weights = {
        "commercial quality": 0.24,
        "professional polish": 0.21,
        "thumbnail visibility": 0.17,
        "typography quality": 0.14,
        "originality": 0.12,
        "visual storytelling": 0.12,
    }
    quality_score = sum(dimensions[name] * weights[name] for name in dimensions) * 10

    platform_values = [
        value
        for key in ("spotify", "apple_music", "youtube_music", "amazon_music", "tiktok")
        if (value := _platform_value(platforms, key)) > 0
    ]
    platform_score = mean(platform_values) if platform_values else quality_score
    score = round(max(0.0, min(100.0, quality_score * 0.82 + platform_score * 0.18)), 1)

    grade, percentile_band, release_readiness = _classification(score)
    passed_gates = [
        label
        for label, value in dimensions.items()
        if value >= _gate_threshold(label)
    ]
    improvement_gaps = [
        f"Raise {label} from {value:.1f} to {_gate_threshold(label):.1f}+"
        for label, value in sorted(dimensions.items(), key=lambda item: item[1])
        if value < _gate_threshold(label)
    ][:3]

    if score >= 85:
        next_action = "Lock the artwork and prepare the full release campaign asset set."
    elif score >= 76:
        next_action = "Run one focused refinement pass on the lowest-scoring dimension."
    elif score >= 66:
        next_action = "Generate a stronger challenger using the listed improvement gaps."
    else:
        next_action = "Rework the core visual premise before production polish."

    if market_lane and score >= 76:
        next_action = f"Position this in the {market_lane} lane, then refine the weakest gate."

    return CommercialBenchmark(
        rubric="Major-label release rubric v1",
        score=score,
        grade=grade,
        percentile_band=percentile_band,
        release_readiness=release_readiness,
        target_score=82.0,
        passed_gates=passed_gates,
        improvement_gaps=improvement_gaps,
        next_action=next_action,
        basis="Internal critic and platform-readiness scores; no live sales or chart data.",
    ).as_dict()


def _score(scores: dict[str, Any], key: str, default: float) -> float:
    try:
        return max(0.0, min(10.0, float(scores.get(key, default))))
    except (TypeError, ValueError):
        return default


def _platform_value(platforms: dict[str, Any], key: str) -> float:
    value = platforms.get(key, 0)
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _gate_threshold(label: str) -> float:
    return {
        "commercial quality": 8.0,
        "professional polish": 7.8,
        "thumbnail visibility": 7.5,
        "typography quality": 7.3,
        "originality": 7.0,
        "visual storytelling": 7.0,
    }[label]


def _classification(score: float) -> tuple[str, str, str]:
    if score >= 90:
        return "A+", "elite internal band", "campaign-ready"
    if score >= 85:
        return "A", "top internal band", "release-ready"
    if score >= 80:
        return "A-", "upper competitive band", "near release-ready"
    if score >= 75:
        return "B+", "competitive band", "one refinement pass"
    if score >= 68:
        return "B", "developing competitive band", "needs focused refinement"
    if score >= 60:
        return "C+", "development band", "needs material refinement"
    return "C", "early development band", "rework recommended"
