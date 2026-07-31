from __future__ import annotations

from typing import Any


# Typography is intentionally separated from image generation.  Image models are
# great at art direction but still unreliable for exact release text.  These
# profiles let the compositor keep spelling deterministic while varying the
# lettering treatment like a real record-sleeve designer.
_GENRE_STYLE_POOLS: dict[str, tuple[str, ...]] = {
    "hip-hop / trap": (
        "street_script",
        "slanted_serif",
        "marker_signature",
        "editorial_italic",
        "vintage_arc",
    ),
    "R&B / soul": (
        "luxury_script",
        "editorial_italic",
        "vintage_arc",
        "marker_signature",
        "slanted_serif",
    ),
    "country / americana": (
        "vintage_arc",
        "heritage_script",
        "slanted_serif",
        "marker_signature",
        "editorial_italic",
    ),
    "acoustic / singer-songwriter": (
        "heritage_script",
        "marker_signature",
        "vintage_arc",
        "editorial_italic",
        "slanted_serif",
    ),
    "rock / alternative": (
        "marker_signature",
        "slanted_serif",
        "vintage_arc",
        "street_script",
        "editorial_italic",
    ),
    "electronic / dance": (
        "editorial_italic",
        "slanted_serif",
        "street_script",
        "vintage_arc",
        "marker_signature",
    ),
    "pop": (
        "luxury_script",
        "editorial_italic",
        "marker_signature",
        "vintage_arc",
        "slanted_serif",
    ),
    "ambient": (
        "editorial_italic",
        "heritage_script",
        "vintage_arc",
        "slanted_serif",
        "marker_signature",
    ),
    "cinematic / experimental": (
        "slanted_serif",
        "vintage_arc",
        "marker_signature",
        "editorial_italic",
        "luxury_script",
    ),
}


def choose_typography_style(signal: dict[str, Any] | None, position: int) -> str:
    """Return a deterministic, genre-aware lettering style for a variation."""
    genre = str((signal or {}).get("inferred_genre") or "cinematic / experimental")
    pool = _GENRE_STYLE_POOLS.get(genre, _GENRE_STYLE_POOLS["cinematic / experimental"])
    return pool[(max(1, position) - 1) % len(pool)]


def typography_direction(signal: dict[str, Any] | None, position: int) -> str:
    """Human-readable direction stored in prompts/tests and useful for audits."""
    style = choose_typography_style(signal, position)
    descriptions = {
        "street_script": "expressive street-script lettering with energetic hand-painted motion",
        "luxury_script": "elegant flowing script-signature lettering with editorial restraint",
        "heritage_script": "warm heritage script inspired by vintage record sleeves and hand-painted signage",
        "marker_signature": "raw handwritten marker lettering with natural irregularity",
        "vintage_arc": "arched vintage display lettering with individual character rotation",
        "editorial_italic": "high-fashion serif italic lettering with offset editorial composition",
        "slanted_serif": "dramatic slanted serif lettering with layered shadow and print depth",
    }
    return descriptions[style]
