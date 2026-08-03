from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlatformScore:
    platform: str
    score: float
    strengths: list[str]
    risks: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_platforms(scores: dict[str, float]) -> dict[str, PlatformScore]:
    thumb = float(scores.get("thumbnail_visibility", scores.get("thumbnail_score", 5)))
    type_score = float(scores.get("typography_quality", 5))
    polish = float(scores.get("professional_polish", 5))
    story = float(scores.get("visual_storytelling", 5))
    commercial = float(scores.get("commercial_quality", 5))

    formulas = {
        "spotify": thumb * 0.45 + type_score * 0.20 + polish * 0.20 + commercial * 0.15,
        "apple_music": polish * 0.35 + type_score * 0.20 + story * 0.20 + commercial * 0.25,
        "youtube_music": thumb * 0.35 + story * 0.30 + commercial * 0.20 + polish * 0.15,
        "amazon_music": commercial * 0.35 + thumb * 0.25 + polish * 0.25 + type_score * 0.15,
        "tiktok": thumb * 0.30 + story * 0.35 + commercial * 0.15 + polish * 0.20,
    }
    result: dict[str, PlatformScore] = {}
    for platform, raw in formulas.items():
        score = round(max(1.0, min(10.0, raw)) * 10, 2)
        strengths = []
        risks = []
        if thumb >= 7.5:
            strengths.append("strong small-format recognition")
        elif thumb < 6:
            risks.append("weak thumbnail recognition")
        if type_score >= 7.5:
            strengths.append("disciplined typography")
        elif type_score < 6:
            risks.append("type may collapse on small screens")
        if story >= 7.5:
            strengths.append("clear visual story")
        if polish < 6:
            risks.append("finish may feel less premium")
        result[platform] = PlatformScore(platform, score, strengths, risks)
    return result
