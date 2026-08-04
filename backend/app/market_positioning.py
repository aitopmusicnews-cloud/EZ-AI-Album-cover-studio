from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .commercial_benchmarking import benchmark_cover


@dataclass(frozen=True, slots=True)
class MarketPositioning:
    lane: str
    target_audience: str
    release_signal: str
    campaign_uses: list[str]
    differentiation: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def position_cover(
    *,
    critic_scores: dict[str, Any] | None,
    platform_scores: dict[str, Any] | None,
    concept_name: str | None,
    genre: str | None,
    mood: str | None,
) -> dict[str, Any]:
    """Translate critic results into a concise commercial market position.

    This is intentionally deterministic so positioning is available even when an
    external model is unavailable. It does not claim live chart or competitor data.
    """
    scores = critic_scores or {}
    platforms = platform_scores or {}

    commercial = _score(scores, "commercial_quality", 5.0)
    polish = _score(scores, "professional_polish", 5.0)
    originality = _score(scores, "originality", 5.0)
    story = _score(scores, "visual_storytelling", 5.0)
    thumbnail = _score(scores, "thumbnail_visibility", 5.0)
    typography = _score(scores, "typography_quality", 5.0)

    if commercial >= 8.0 and polish >= 7.5:
        lane = "Major-label mainstream"
        release_signal = "Premium, release-ready and broadly accessible"
    elif originality >= 8.0 and story >= 7.5:
        lane = "Editorial / culture-forward"
        release_signal = "Distinctive, story-led and press-friendly"
    elif thumbnail >= 8.0 and _platform_value(platforms, "tiktok") >= 75:
        lane = "Social-first breakout"
        release_signal = "Immediate, scroll-stopping and campaign-flexible"
    elif typography >= 7.5 and polish >= 7.0:
        lane = "Premium independent"
        release_signal = "Designed, credible and niche-to-mainstream ready"
    else:
        lane = "Developing independent"
        release_signal = "Promising direction that benefits from another refinement pass"

    target_audience = _audience(genre, mood)
    campaign_uses = _campaign_uses(platforms, thumbnail, story, polish)
    differentiation = _differentiation(
        concept_name=concept_name,
        originality=originality,
        story=story,
        thumbnail=thumbnail,
        typography=typography,
        polish=polish,
    )
    confidence = round(
        max(0.0, min(100.0, (commercial + polish + originality + story + thumbnail) * 2.0)),
        1,
    )

    positioning = MarketPositioning(
        lane=lane,
        target_audience=target_audience,
        release_signal=release_signal,
        campaign_uses=campaign_uses,
        differentiation=differentiation,
        confidence=confidence,
    ).as_dict()
    positioning["commercial_benchmark"] = benchmark_cover(
        critic_scores=scores,
        platform_scores=platforms,
        market_lane=lane,
    )
    return positioning


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
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _audience(genre: str | None, mood: str | None) -> str:
    genre_text = (genre or "genre-fluid").strip()
    mood_text = (mood or "emotionally driven").strip()
    return f"Listeners drawn to {genre_text} releases with a {mood_text} visual identity"


def _campaign_uses(
    platforms: dict[str, Any], thumbnail: float, story: float, polish: float
) -> list[str]:
    candidates = sorted(
        (
            (_platform_value(platforms, "spotify"), "DSP thumbnail and playlist pitching"),
            (_platform_value(platforms, "apple_music"), "premium storefront placement"),
            (_platform_value(platforms, "youtube_music"), "video thumbnail and visualizer rollout"),
            (_platform_value(platforms, "tiktok"), "short-form teaser and social launch"),
            (_platform_value(platforms, "amazon_music"), "broad retail and catalog presentation"),
        ),
        reverse=True,
    )
    uses = [label for score, label in candidates if score >= 65][:3]
    if not uses:
        if thumbnail >= 7:
            uses.append("DSP thumbnail and playlist pitching")
        if story >= 7:
            uses.append("visualizer and narrative campaign assets")
        if polish >= 7:
            uses.append("press kit and release announcement")
    return uses or ["organic release testing before paid campaign expansion"]


def _differentiation(
    *,
    concept_name: str | None,
    originality: float,
    story: float,
    thumbnail: float,
    typography: float,
    polish: float,
) -> str:
    dimensions = {
        "original concept": originality,
        "visual storytelling": story,
        "thumbnail recognition": thumbnail,
        "typographic discipline": typography,
        "professional finish": polish,
    }
    strongest = max(dimensions, key=dimensions.get)
    prefix = f"{concept_name}: " if concept_name else ""
    return f"{prefix}stands out most through {strongest}."
